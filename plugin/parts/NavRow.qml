import QtQuick
import qs.Commons
import qs.Ui

// A row that opens a page (›), with its explainer underneath (BUILD 3.2).
CursorSurface {
  id: row
  property string title: ""
  property string explainer: ""
  property bool hasCursorHere: false
  property bool enabledRow: true
  signal activated()
  hasCursor: hasCursorHere
  width: parent ? parent.width : 300
  implicitHeight: column.implicitHeight + Style.space(14)
  opacity: enabledRow ? 1 : 0.55

  function activate() { if (enabledRow) activated() }

  Column {
    id: column
    anchors.left: parent.left
    anchors.right: chevron.left
    anchors.verticalCenter: parent.verticalCenter
    anchors.margins: Style.space(10)
    spacing: Style.space(2)
    Prose { width: parent.width; text: row.title }
    Prose { width: parent.width; visible: text !== ""; text: row.explainer; dim: true }
  }
  Prose {
    id: chevron
    visible: row.enabledRow
    anchors.right: parent.right
    anchors.rightMargin: Style.space(12)
    anchors.verticalCenter: parent.verticalCenter
    text: "›"
    wrapMode: Text.NoWrap
  }
  MouseArea { anchors.fill: parent; enabled: row.enabledRow; onClicked: row.activated() }
}
