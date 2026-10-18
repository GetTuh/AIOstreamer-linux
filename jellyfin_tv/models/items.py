import re
import unicodedata

from PySide6.QtCore import Property, QAbstractListModel, QByteArray, QModelIndex, Qt, QTimer, Signal, Slot

from jellyfin_tv.api.images import image_source
from jellyfin_tv.api.meta import episode_label, runtime_text
from jellyfin_tv.models.services import services

ROLE_NAMES = (
    "itemId", "name", "subtitle", "itemType", "stremioType", "seriesId", "image", "progress",
    "played", "unplayedCount", "isFolder", "overview", "favorite",
)
ROLES = {Qt.UserRole + i: name for i, name in enumerate(ROLE_NAMES)}


def subtitle_for(item):
    kind = item.get("type")
    if kind == "Episode":
        return " · ".join(p for p in (episode_label(item), item.get("name")) if p)
    if kind == "Catalog":
        return item.get("subtitle", "")
    return item.get("year") or ""


def title_for(item):
    if item.get("type") == "Episode" and item.get("seriesName"):
        return item["seriesName"]
    return item.get("name", "")


def history():
    library = services.library
    return library.history if library is not None else None


def progress_for(item):
    state = history()
    return state.fraction(item.get("id", "")) if state is not None else 0.0


def played_for(item):
    if "played" in item:
        return bool(item["played"])
    state = history()
    return bool(state is not None and state.watched(item.get("id", "")))


def normalize_title(text):
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def match_score(term, title):
    term = normalize_title(term)
    title = normalize_title(title)
    if not term or not title:
        return 0.0
    if title == term:
        return 4.0
    if title.startswith(term + " ") or title.startswith(term):
        return 3.0 - min(len(title) - len(term), 40) / 100.0
    words = term.split()
    if all(w in title.split() for w in words):
        return 2.0
    if all(w in title for w in words):
        return 1.5
    return 1.0 if any(w in title for w in words) else 0.0


class ItemListModel(QAbstractListModel):
    countChanged = Signal()
    loadingChanged = Signal()
    kindChanged = Signal()

    def __init__(self, runner, fetch, image_kind="poster", page_size=0, title="", parent=None, context="default", peek=None):
        super().__init__(parent)
        self._runner = runner
        self._fetch = fetch
        self._peek = peek
        self._kind = image_kind
        self._page = page_size
        self._title = title
        self._context = context
        self._items = []
        self._total = 0
        self._loading = False
        self._loaded = False
        self._generation = 0

    def roleNames(self):
        return {k: QByteArray(v.encode()) for k, v in ROLES.items()}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._items)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._items):
            return None
        item = self._items[index.row()]
        name = ROLES.get(role)
        if name is None:
            return item.get("name") if role == Qt.DisplayRole else None
        return self._value(item, name)

    def _value(self, item, name):
        if name == "itemId":
            return item.get("id")
        if name == "name":
            if self._context == "episodes":
                number = item.get("episode")
                return "%s. %s" % (number, item.get("name", "")) if number is not None else item.get("name", "")
            return title_for(item)
        if name == "subtitle":
            if self._context == "episodes":
                return runtime_text(item.get("runtime"))
            return subtitle_for(item)
        if name == "itemType":
            return item.get("type", "")
        if name == "stremioType":
            return item.get("stremioType", "")
        if name == "seriesId":
            return item.get("seriesId", "")
        if name == "image":
            return image_source(item, self._kind)
        if name == "progress":
            return progress_for(item)
        if name == "overview":
            return item.get("overview") or ""
        if name == "played":
            return played_for(item)
        if name == "unplayedCount":
            return int(item.get("unplayed") or 0)
        if name == "favorite":
            state = history()
            return bool(state is not None and state.favorite(item.get("id", "")))
        if name == "isFolder":
            return item.get("type") == "Catalog"
        return None

    @Property(str, constant=True)
    def title(self):
        return self._title

    def _get_kind(self):
        return self._kind

    def _set_kind(self, value):
        if value and value != self._kind:
            self._kind = value
            self.kindChanged.emit()
            self.refreshUserData()

    imageKind = Property(str, _get_kind, _set_kind, notify=kindChanged)

    @Property(int, notify=countChanged)
    def count(self):
        return len(self._items)

    @Property(bool, notify=loadingChanged)
    def loading(self):
        return self._loading

    @Property(bool, notify=loadingChanged)
    def loaded(self):
        return self._loaded

    def _set_loading(self, value):
        self._loading = value
        self.loadingChanged.emit()

    def _apply(self, items, total):
        items = list(items)
        same = len(items) == len(self._items) and all(
            a.get("id") == b.get("id") for a, b in zip(items, self._items))
        if same and items:
            self._items = items
            self.dataChanged.emit(self.index(0), self.index(len(items) - 1))
        else:
            self.beginResetModel()
            self._items = items
            self.endResetModel()
        self._total = total if total else len(self._items)

    def _peek_cached(self):
        if self._peek is None or self._items:
            return
        try:
            cached = self._peek()
        except Exception:
            cached = None
        if cached:
            self._apply(*cached)
            self._loaded = True
            self.countChanged.emit()

    @Slot()
    def reload(self):
        self._generation += 1
        generation = self._generation
        self._peek_cached()
        self._set_loading(True)
        limit = self._page or None
        if self._page and len(self._items) > self._page:
            limit = len(self._items)

        def done(result):
            if generation != self._generation:
                return
            self._apply(*result)
            self._loaded = True
            self._set_loading(False)
            self.countChanged.emit()

        def failed(_exc):
            if generation == self._generation:
                self._loaded = True
                self._set_loading(False)

        self._runner.run(lambda: self._fetch(0, limit), done, failed)

    @Slot()
    def refreshUserData(self):
        if self._items:
            self.dataChanged.emit(self.index(0), self.index(len(self._items) - 1))

    @Slot()
    def clear(self):
        self._generation += 1
        self.beginResetModel()
        self._items = []
        self._total = 0
        self.endResetModel()
        self._loaded = False
        self._set_loading(False)
        self.countChanged.emit()

    def canFetchMore(self, parent=QModelIndex()):
        return bool(self._page) and self._loaded and not self._loading and len(self._items) < self._total

    def fetchMore(self, parent=QModelIndex()):
        if not self.canFetchMore():
            return
        generation = self._generation
        start = len(self._items)
        self._set_loading(True)

        def done(result):
            if generation != self._generation:
                return
            items, total = result
            known = {i.get("id") for i in self._items}
            items = [i for i in items if i.get("id") not in known]
            if items:
                self.beginInsertRows(QModelIndex(), start, start + len(items) - 1)
                self._items.extend(items)
                self.endInsertRows()
            self._total = total if items else len(self._items)
            self._set_loading(False)
            self.countChanged.emit()

        def failed(_exc):
            if generation == self._generation:
                self._total = len(self._items)
                self._set_loading(False)

        self._runner.run(lambda: self._fetch(start, self._page), done, failed)

    @Slot(int, result="QVariantMap")
    def get(self, row):
        if row < 0 or row >= len(self._items):
            return {}
        item = self._items[row]
        out = {name: self._value(item, name) for name in ROLE_NAMES}
        out["catalog"] = item.get("catalog") or {}
        return out

    @Slot(str, result=int)
    def indexOf(self, item_id):
        for row, item in enumerate(self._items):
            if item.get("id") == item_id:
                return row
        return -1

    def raw(self, row):
        return self._items[row] if 0 <= row < len(self._items) else None

    @property
    def items(self):
        return self._items


class LibraryModel(ItemListModel):
    PAGE_SIZE = 50

    paramsChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(services.runner, self._fetch_page, "poster", self.PAGE_SIZE, "", parent, peek=self._peek_page)
        self._type = ""
        self._catalog = ""
        self._genres = []
        self._required = False
        self._genre = ""

    def _extra(self):
        return {"genre": self._genre} if self._genre else None

    def _fetch_page(self, start, limit):
        return services.library.catalog(self._type, self._catalog, self._extra(), start, limit)

    def _peek_page(self):
        items = services.library.peek_catalog(self._type, self._catalog, self._extra())
        return (items, len(items) + 1) if items else None

    def _setter(attr):
        def setter(self, value):
            if value != getattr(self, attr):
                setattr(self, attr, value)
                self.paramsChanged.emit()
        return setter

    def _set_genres(self, value):
        value = list(value or [])
        if value != self._genres:
            self._genres = value
            if self._required and not self._genre and value:
                self._genre = value[0]
            self.paramsChanged.emit()

    def _set_required(self, value):
        if bool(value) != self._required:
            self._required = bool(value)
            if self._required and not self._genre and self._genres:
                self._genre = self._genres[0]
            self.paramsChanged.emit()

    def _set_genre(self, value):
        if value != self._genre:
            self._genre = value
            self.paramsChanged.emit()
            self.clear()
            self.reload()

    catalogType = Property(str, lambda self: self._type, _setter("_type"), notify=paramsChanged)
    catalogId = Property(str, lambda self: self._catalog, _setter("_catalog"), notify=paramsChanged)
    genres = Property("QVariantList", lambda self: self._genres, _set_genres, notify=paramsChanged)
    genreRequired = Property(bool, lambda self: self._required, _set_required, notify=paramsChanged)
    genre = Property(str, lambda self: self._genre, _set_genre, notify=paramsChanged)

    @Slot(int)
    def stepGenre(self, step):
        choices = list(self._genres) if self._required else [""] + list(self._genres)
        if not choices:
            return
        index = choices.index(self._genre) if self._genre in choices else 0
        self._set_genre(choices[(index + step) % len(choices)])

    @Property(str, notify=paramsChanged)
    def genreName(self):
        return self._genre or "All"


class SearchModel(ItemListModel):
    DEBOUNCE_MS = 450
    MIN_CHARS = 2

    paramsChanged = Signal()
    relevanceChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(services.runner, self._fetch_search, "poster", 0, "", parent)
        self._term = ""
        self._types = "Movie"
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(self.DEBOUNCE_MS)
        self._timer.timeout.connect(self._run)
        self.countChanged.connect(self.relevanceChanged)

    def _fetch_search(self, start, limit):
        term = self._term.strip()
        items = services.library.search(term, self._types)
        items.sort(key=lambda i: match_score(term, i.get("name", "")), reverse=True)
        return items, len(items)

    def _run(self):
        if len(self._term.strip()) < self.MIN_CHARS:
            self.clear()
        else:
            self.reload()

    def _get_term(self):
        return self._term

    def _set_term(self, value):
        if value != self._term:
            self._term = value
            self.paramsChanged.emit()
            self._timer.start()

    def _get_types(self):
        return self._types

    def _set_types(self, value):
        if value and value != self._types:
            self._types = value
            self.paramsChanged.emit()

    @Property(float, notify=relevanceChanged)
    def relevance(self):
        best = 0.0
        for rank, item in enumerate(self._items[:5]):
            best = max(best, match_score(self._term, item.get("name", "")) - rank * 0.05)
        return best

    term = Property(str, _get_term, _set_term, notify=paramsChanged)
    itemTypes = Property(str, _get_types, _set_types, notify=paramsChanged)
