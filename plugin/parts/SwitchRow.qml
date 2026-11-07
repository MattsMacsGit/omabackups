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

  Column {
    id: column
    anchors.left: parent.left
    anchors.right: parent.right
    anchors.top: parent.top
    anchors.margins: Style.space(10)
    spacing: Style.space(4)
    Item {
      width: parent.width
      implicitHeight: Math.max(titleText.implicitHeight, toggle.implicitHeight)
      Prose { id: titleText; anchors.left: parent.left; anchors.right: gear.left; text: row.title }
      PanelActionButton {
        id: gear
        visible: row.hasGear
        anchors.right: toggle.left
        anchors.rightMargin: Style.space(6)
        anchors.verticalCenter: parent.verticalCenter
        iconText: ""
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
    Prose { width: parent.width; visible: text !== ""; text: row.explainer; dim: true }
    Column { id: optionsColumn; visible: row.gearOpen; width: parent.width; spacing: Style.space(6) }
  }
}
