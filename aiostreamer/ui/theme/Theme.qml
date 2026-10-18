pragma Singleton
import QtQuick

QtObject {
    property color background: "#0f1218"
    property color surface: "#1a1f29"
    property color surfaceHigh: "#262d3a"
    property color text: "#f3f5f9"
    property color textDim: "#a3abba"
    property color accent: "#3daee9"
    property color focus: "#ffffff"
    property color focusText: "#0f1218"
    property color danger: "#e5534b"
    property color scrim: "#cc0b0e13"

    property int margin: 72
    property int spacing: 24
    property int radius: 8
    property real focusScale: 1.08
    property int animMs: 140

    property int posterWidth: 200
    property int posterHeight: 300
    property int thumbWidth: 360
    property int thumbHeight: 202
    property int labelHeight: 62

    property int fontSmall: 18
    property int fontBody: 22
    property int fontButton: 24
    property int fontRow: 28
    property int fontTitle: 46
    property int fontHuge: 64
}
