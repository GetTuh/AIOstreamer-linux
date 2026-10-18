from PySide6.QtCore import Property, QAbstractListModel, QByteArray, QModelIndex, Qt, Signal, Slot

from aiostreamer.models.items import ItemListModel

ROW_LIMIT = 24
LOCAL_ROWS = ("resume", "nextup", "favorites")


class HomeModel(QAbstractListModel):
    TitleRole = Qt.UserRole + 1
    ModelRole = Qt.UserRole + 2
    KeyRole = Qt.UserRole + 3

    countChanged = Signal()

    def __init__(self, runner, library, parent=None):
        super().__init__(parent)
        self._runner = runner
        self._library = library
        self._rows = []
        self._catalogs = None

    def roleNames(self):
        return {
            self.TitleRole: QByteArray(b"title"),
            self.ModelRole: QByteArray(b"rowModel"),
            self.KeyRole: QByteArray(b"rowKey"),
        }

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._rows):
            return None
        key, model = self._rows[index.row()]
        if role == self.TitleRole:
            return model.title
        if role == self.ModelRole:
            return model
        if role == self.KeyRole:
            return key
        return None

    @Property(int, notify=countChanged)
    def count(self):
        return len(self._rows)

    def _row(self, key, title, fetch, kind, peek=None):
        return key, ItemListModel(self._runner, fetch, kind, title=title, parent=self, peek=peek)

    @staticmethod
    def _wrap(items):
        items = list(items)
        return items, len(items)

    @Slot()
    def load(self):
        lib = self._library
        rows = [
            self._row("resume", "Continue Watching", lambda s, n: self._wrap(lib.resume(ROW_LIMIT)), "thumb"),
            self._row("nextup", "Next Up", lambda s, n: self._wrap(lib.next_up(ROW_LIMIT)), "thumb"),
            self._row("favorites", "My List", lambda s, n: self._wrap(lib.favorites()), "poster"),
        ]
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()
        self.countChanged.emit()
        for _, model in rows:
            model.reload()
        try:
            cached = lib.client.peek_manifest()
        except Exception:
            cached = None
        if cached:
            try:
                self._on_catalogs(lib.home_catalogs())
            except Exception:
                pass
        self._runner.run(lib.home_catalogs, self._on_catalogs)

    @staticmethod
    def _catalog_entry(row):
        return {
            "id": row["key"], "type": "Catalog", "name": row["title"],
            "subtitle": row["extra"]["genre"] if row.get("extra") else "",
            "catalog": {"type": row["type"], "id": row["id"], "title": row["title"],
                        "genres": row["genres"], "genreRequired": row["genreRequired"]},
        }

    def _on_catalogs(self, catalogs):
        signature = [(c["key"], c["title"], str(c["extra"])) for c in catalogs]
        if signature == self._catalogs:
            return
        self._catalogs = signature
        lib = self._library
        rows = []
        for c in catalogs:
            def fetch(s, n, c=c):
                return lib.catalog(c["type"], c["id"], c["extra"], 0, ROW_LIMIT)

            def peek(c=c):
                items = lib.peek_catalog(c["type"], c["id"], c["extra"])
                return (items, len(items)) if items else None

            rows.append(self._row(c["key"], c["title"], fetch, "poster", peek))
        entries = [self._catalog_entry(c) for c in catalogs]
        rows.append(self._row("catalogs", "Browse", lambda s, n, e=entries: self._wrap(e), "thumb"))
        local = [r for r in self._rows if r[0] in LOCAL_ROWS]
        self.beginResetModel()
        self._rows = local + rows
        self.endResetModel()
        self.countChanged.emit()
        for _, model in rows:
            model.reload()

    @Slot()
    def refreshPlayback(self):
        for key, model in self._rows:
            if key in LOCAL_ROWS:
                model.reload()
            else:
                model.refreshUserData()

    @Slot()
    def refreshCatalogs(self):
        for key, model in self._rows:
            if key not in LOCAL_ROWS:
                model.reload()
