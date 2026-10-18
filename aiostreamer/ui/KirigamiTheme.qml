import QtQuick
import org.kde.kirigami as Kirigami
import "theme"

Item {
    Component.onCompleted: {
        Theme.accent = Kirigami.Theme.highlightColor
    }
}
