import QtQuick
import qs.Ui

// A small button inside a setting (a gear's options, − and +) that the
// keyboard cursor can reach too.
Button {
  property var owner: null
  bordered: true
  hasCursor: owner ? owner.cursorOn(this) : false
  function activate() { clicked() }
}
