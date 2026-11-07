import QtQuick
import qs.Commons
import qs.Ui

// A real switch (1.x rule); a gear only shows that switch's own options.
CursorSurface {
  id: row
  property string title: ""
  property string explainer: ""
  property bool checked: false
  property bool hasGear: false
  property bool gearOpen: false
  property bool hasCursorHere: false
  property alias options: optionsColumn.data
  signal toggled()
  hasCursor: hasCursorHere
  width: parent ? parent.width : 300
  implicitHeight: column.implicitHeight + Style.space(14)

  function activate() { toggled() }
  function openOptions() { if (hasGear) gearOpen = !gearOpen }

  Column {
    id: column
    anchors.left: parent.left
    anchors.right: parent.right
    anchors.top: parent.top
    anchors.margins: Style.space(10)
    spacing: Style.space(4)
    Item {
      width: parent.width
      implicitHeight: Math.max(words.implicitHeight, toggle.implicitHeight)
      Column {
        id: words
        anchors.left: parent.left
        anchors.right: gear.visible ? gear.left : toggle.left
        anchors.rightMargin: Style.space(8)
        anchors.verticalCenter: parent.verticalCenter
        spacing: Style.space(2)
        Prose { width: parent.width; text: row.title }
        Prose { width: parent.width; visible: text !== ""; text: row.explainer; dim: true }
      }
      PanelActionButton {
        id: gear
        visible: row.hasGear
        anchors.right: toggle.left
        anchors.rightMargin: Style.space(6)
        anchors.verticalCenter: parent.verticalCenter
        iconText: "\uf013"
        tooltipText: "Options"
        onClicked: row.gearOpen = !row.gearOpen
      }
      ToggleSwitch {
        id: toggle
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        checked: row.checked
        onToggled: row.toggled()
      }
    }
    Column { id: optionsColumn; visible: row.gearOpen; width: parent.width; spacing: Style.space(6) }
  }
}
