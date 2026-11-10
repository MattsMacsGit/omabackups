import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// A line that appears only when true (BUILD 6.1 D) in its rule colour (7.0):
// red is only ever a problem's one-line title; its explainer is yellow.
CursorSurface {
  id: line
  property var item: ({})
  property var service: null
  property bool hasCursorHere: false
  property alias buttons: buttonRow.data
  // The line's own buttons, for the keyboard (they replace the line as targets).
  readonly property var buttonItems: buttonRow.children
  signal activated()
  hasCursor: hasCursorHere
  width: parent ? parent.width : 300
  implicitHeight: column.implicitHeight + Style.space(14)

  function activate() { activated() }

  readonly property color titleColour: service ? service.colour(item.colour) : Commons.Color.foreground
  readonly property color textColour: item.colour === "red" && service ? service.colour("yellow")
                                                                         : Qt.darker(Commons.Color.foreground, 1.4)

  Column {
    id: column
    anchors.left: parent.left
    anchors.right: parent.right
    anchors.verticalCenter: parent.verticalCenter
    anchors.margins: Style.space(10)
    spacing: Style.space(4)
    Prose { width: parent.width; text: line.item.title || ""; color: line.titleColour; font.bold: true }
    Prose { width: parent.width; visible: text !== ""; text: line.item.text || ""; dim: true; color: line.textColour }
    Flow { id: buttonRow; width: parent.width; spacing: Style.space(8) }
  }
  MouseArea { anchors.fill: parent; z: -1; onClicked: line.activated() }
}
