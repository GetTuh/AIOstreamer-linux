import re
import unicodedata

from PySide6.QtCore import Property, QAbstractListModel, QByteArray, QModelIndex, Qt, QTimer, Signal, Slot

from jellyfin_tv.api.images import image_source
from jellyfin_tv.models.services import services

TICKS = 10_000_000

ROLE_NAMES = (
    "itemId", "name", "subtitle", "itemType", "collectionType", "image", "progress",
    "played", "unplayedCount", "isFolder", "overview", "favorite",
)
ROLES = {Qt.UserRole + i: name for i, name in enumerate(ROLE_NAMES)}

SORTS = (
    ("", "Default", None),
    ("SortName", "Name", "Ascending"),
    ("DateCreated,SortName", "Date added", "Descending"),
    ("PremiereDate,SortName", "Release date", "Descending"),
    ("CommunityRating,SortName", "Rating", "Descending"),
)


def episode_label(item):
    season = item.get("ParentIndexNumber")
    number = item.get("IndexNumber")
    if season is None and number is None:
        return ""
    if season is None:
        return "E%d" % number
    if number is None:
        return "S%d" % season
    return "S%d:E%d" % (season, number)


def runtime_text(ticks):
    minutes = int((ticks or 0) / TICKS / 60)
    if not minutes:
        return ""
    hours, mins = divmod(minutes, 60)
    return "%dh %dm" % (hours, mins) if hours else "%dm" % mins


def subtitle_for(item):
    kind = item.get("Type")
    if kind == "Episode":
        label = episode_label(item)
        return " · ".join(p for p in (label, item.get("Name")) if p)
    if kind == "Series":
        start = item.get("ProductionYear")
        end = (item.get("EndDate") or "")[:4]
        if start and item.get("Status") == "Continuing":
            return "%s –" % start
        if start and end and str(start) != end:
            return "%s – %s" % (start, end)
        return str(start or "")
    if item.get("ProductionYear"):
        return str(item["ProductionYear"])
    return ""


def title_for(item):
    if item.get("Type") == "Episode" and item.get("SeriesName"):
        return item["SeriesName"]
    return item.get("Name", "")


def progress_for(item):
    data = item.get("UserData") or {}
    if data.get("PlayedPercentage") is not None and not data.get("Played"):
        return max(0.0, min(1.0, data["PlayedPercentage"] / 100.0))
    pos = data.get("PlaybackPositionTicks") or 0
    total = item.get("RunTimeTicks") or 0
    if pos and total:
        return max(0.0, min(1.0, pos / total))
    return 0.0


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

    def __init__(self, runner, fetch, image_kind="poster", page_size=0, title="", parent=None, context="default"):
        super().__init__(parent)
        self._runner = runner
        self._fetch = fetch
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
            return item.get("Name") if role == Qt.DisplayRole else None
        return self._value(item, name)

    def _value(self, item, name):
        if name == "itemId":
            return item.get("Id")
        if name == "name":
            if self._context == "episodes":
                number = item.get("IndexNumber")
                return "%s. %s" % (number, item.get("Name", "")) if number is not None else item.get("Name", "")
            return title_for(item)
        if name == "subtitle":
            if self._context == "episodes":
                return runtime_text(item.get("RunTimeTicks"))
            return subtitle_for(item)
        if name == "itemType":
            return item.get("Type", "")
        if name == "collectionType":
            return item.get("CollectionType", "")
        if name == "image":
            return image_source(item, self._kind)
        if name == "progress":
            return progress_for(item)
        if name == "overview":
            return item.get("Overview") or ""
        data = item.get("UserData") or {}
        if name == "played":
            return bool(data.get("Played"))
        if name == "unplayedCount":
            return int(data.get("UnplayedItemCount") or 0)
        if name == "favorite":
            return bool(data.get("IsFavorite"))
        if name == "isFolder":
            return bool(item.get("IsFolder"))
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
            if self._items:
                self.dataChanged.emit(self.index(0), self.index(len(self._items) - 1))

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
            a.get("Id") == b.get("Id") for a, b in zip(items, self._items))
        if same and items:
            self._items = items
            self.dataChanged.emit(self.index(0), self.index(len(items) - 1))
        else:
            self.beginResetModel()
            self._items = items
            self.endResetModel()
        self._total = total if total else len(self._items)

    @Slot()
    def reload(self):
        self._generation += 1
        generation = self._generation
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
            items = list(items)
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
        return {name: self._value(item, name) for name in ROLE_NAMES}

    @Slot(str, result=int)
    def indexOf(self, item_id):
        for row, item in enumerate(self._items):
            if item.get("Id") == item_id:
                return row
        return -1

    def raw(self, row):
        return self._items[row] if 0 <= row < len(self._items) else None

    @property
    def items(self):
        return self._items


class LibraryModel(ItemListModel):
    PAGE_SIZE = 60

    paramsChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(services.runner, self._fetch_page, "poster", self.PAGE_SIZE, "", parent)
        self._parent_id = ""
        self._collection_type = ""
        self._sort = 0

    def _fetch_page(self, start, limit):
        sort_by, _, order = SORTS[self._sort]
        return services.library.items(self._parent_id, self._collection_type, start, limit, sort_by or None, order)

    def _get_parent(self):
        return self._parent_id

    def _set_parent(self, value):
        if value != self._parent_id:
            self._parent_id = value
            self.paramsChanged.emit()

    def _get_collection(self):
        return self._collection_type

    def _set_collection(self, value):
        if value != self._collection_type:
            self._collection_type = value
            self.paramsChanged.emit()

    def _get_sort(self):
        return self._sort

    def _set_sort(self, value):
        value = int(value) % len(SORTS)
        if value != self._sort:
            self._sort = value
            self.paramsChanged.emit()
            self.clear()
            self.reload()

    parentId = Property(str, _get_parent, _set_parent, notify=paramsChanged)
    collectionType = Property(str, _get_collection, _set_collection, notify=paramsChanged)
    sortIndex = Property(int, _get_sort, _set_sort, notify=paramsChanged)

    @Property(str, notify=paramsChanged)
    def sortName(self):
        return SORTS[self._sort][1]


class SimilarModel(ItemListModel):
    paramsChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(services.runner, self._fetch_similar, "thumb", 0, "More like this", parent)
        self._item_id = ""

    def _fetch_similar(self, start, limit):
        items = services.library.similar(self._item_id)
        return items, len(items)

    def _get_item(self):
        return self._item_id

    def _set_item(self, value):
        if value != self._item_id:
            self._item_id = value
            self.paramsChanged.emit()
            if value:
                self.reload()

    itemId = Property(str, _get_item, _set_item, notify=paramsChanged)


class SearchModel(ItemListModel):
    DEBOUNCE_MS = 350
    MIN_CHARS = 2

    paramsChanged = Signal()
    relevanceChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(services.runner, self._fetch_search, "poster", 0, "", parent)
        self._term = ""
        self._types = "Movie,Series"
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(self.DEBOUNCE_MS)
        self._timer.timeout.connect(self._run)
        self.countChanged.connect(self.relevanceChanged)

    def _fetch_search(self, start, limit):
        items = services.library.search(self._term, self._types)
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
            best = max(best, match_score(self._term, item.get("Name", "")) - rank * 0.05)
        return best

    term = Property(str, _get_term, _set_term, notify=paramsChanged)
    itemTypes = Property(str, _get_types, _set_types, notify=paramsChanged)
