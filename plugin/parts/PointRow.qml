import QtQuick
import qs.Commons
import qs.Ui

// One restore point (D37): the whole row opens it in the file manager.
CursorSurface {
  id: row
  property string title: ""
  property string tag: ""             // "kept", "Return point", "Opening…", "Open"
  property bool hasCursorHere: false
  signal activated()
  hasCursor: hasCursorHere
  width: parent ? parent.width : 300
  implicitHeight: label.implicitHeight + Style.space(14)

  function activate() { activated() }

  Prose {
    id: label
    anchors.left: parent.left
    anchors.right: tagText.left
    anchors.leftMargin: Style.space(10)
    anchors.rightMargin: Style.space(8)
    anchors.verticalCenter: parent.verticalCenter
    text: row.title
    wrapMode: Text.NoWrap
    elide: Text.ElideRight
  }
  Prose {
    id: tagText
    anchors.right: chevron.left
    anchors.rightMargin: Style.space(8)
    anchors.verticalCenter: parent.verticalCenter
    dim: true
    wrapMode: Text.NoWrap
    text: row.tag
  }
  Prose {
    id: chevron
    anchors.right: parent.right
    anchors.rightMargin: Style.space(12)
    anchors.verticalCenter: parent.verticalCenter
    text: "›"
    wrapMode: Text.NoWrap
  }
  MouseArea { anchors.fill: parent; onClicked: row.activated() }
}
