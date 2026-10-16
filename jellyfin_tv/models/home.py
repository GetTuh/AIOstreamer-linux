from PySide6.QtCore import Property, QAbstractListModel, QByteArray, QModelIndex, Qt, Signal, Slot

from jellyfin_tv.models.items import ItemListModel

ROW_LIMIT = 24


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
        self._views = []

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

    def _row(self, key, title, fetch, kind):
        return key, ItemListModel(self._runner, fetch, kind, title=title, parent=self)

    @Slot()
    def load(self):
        lib = self._library
        rows = [
            self._row("resume", "Continue Watching", lambda s, n: self._wrap(lib.resume(ROW_LIMIT)), "thumb"),
            self._row("nextup", "Next Up", lambda s, n: self._wrap(lib.next_up(ROW_LIMIT)), "thumb"),
            self._row("favorites", "Favorites", lambda s, n: self._wrap(lib.favorites(ROW_LIMIT)), "poster"),
        ]
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()
        self.countChanged.emit()
        for _, model in rows:
            model.reload()
        self._runner.run(lib.views, self._on_views)

    @staticmethod
    def _wrap(items):
        return items, len(items)

    def _on_views(self, views):
        lib = self._library
        self._views = views
        rows = [self._row("views", "My Media", lambda s, n, v=views: self._wrap(v), "thumb")]
        for view in views:
            vid = view["Id"]
            ctype = view.get("CollectionType")
            rows.append(self._row(
                "view:" + vid, view.get("Name", ""),
                lambda s, n, vid=vid, ctype=ctype: lib.items(vid, ctype, 0, ROW_LIMIT),
                "poster"))
        start = len(self._rows)
        self.beginInsertRows(QModelIndex(), start, start + len(rows) - 1)
        self._rows.extend(rows)
        self.endInsertRows()
        self.countChanged.emit()
        for _, model in rows:
            model.reload()

    @Slot()
    def refreshPlayback(self):
        for key, model in self._rows:
            if key in ("resume", "nextup", "favorites"):
                model.reload()
