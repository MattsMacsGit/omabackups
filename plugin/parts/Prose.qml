import QtQuick
import qs.Commons
import qs.Commons as Commons

// Plain text only (Omarchy's plugin safety rule: never markup from data).
Text {
  property bool dim: false
  property color baseColor: Commons.Color.foreground
  textFormat: Text.PlainText
  wrapMode: Text.WordWrap
  color: dim ? Qt.darker(baseColor, 1.55) : baseColor
  font.family: Style.font.family
  font.pixelSize: dim ? Style.font.bodySmall : Style.font.body
}
