import QtQuick
import qs.Commons
import qs.Ui

// A real switch (1.x rule): the whole row flips it. The gear, at the far end
// and only while the switch is on, shows that switch's own options (D32).
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
  implicitHeight: column.implicitHeight + Style.space(16)

  readonly property bool gearShown: hasGear && checked
  function activate() { toggled() }
  function openOptions() { if (gearShown) gearOpen = !gearOpen }

  // Under everything else: a click anywhere on the row flips the switch.
  MouseArea { anchors.fill: parent; onClicked: row.toggled() }

  Column {
    id: column
    anchors.left: parent.left
    anchors.right: parent.right
    anchors.top: parent.top
    anchors.margins: Style.space(10)
    anchors.topMargin: Style.space(8)
    spacing: Style.space(8)
    Item {
      width: parent.width
      implicitHeight: Math.max(words.implicitHeight, toggle.implicitHeight)
      Column {
        id: words
        anchors.left: parent.left
        anchors.right: toggle.left
        anchors.rightMargin: Style.space(10)
        anchors.verticalCenter: parent.verticalCenter
        spacing: Style.space(2)
        Prose { width: parent.width; text: row.title }
        Prose { width: parent.width; visible: text !== ""; text: row.explainer; dim: true }
      }
      ToggleSwitch {
        id: toggle
        anchors.right: gear.visible ? gear.left : parent.right
        anchors.rightMargin: gear.visible ? Style.space(8) : 0
        anchors.verticalCenter: parent.verticalCenter
        checked: row.checked
        onToggled: row.toggled()
      }
      Button {
        id: gear
        visible: row.gearShown
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        iconText: "\uf013"
        bordered: true
        selected: row.gearOpen
        tooltipText: "Options"
        onClicked: row.gearOpen = !row.gearOpen
      }
    }
    Column { id: optionsColumn; visible: row.gearShown && row.gearOpen; width: parent.width; spacing: Style.space(6) }
  }
}
