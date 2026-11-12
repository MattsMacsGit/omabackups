.pragma library

// Words for dates and sizes, said the same way everywhere (BUILD 7.0:
// "Latest backup was Tuesday 12:33 pm", never "from <restore point>").

function clock(d) {
  var h = d.getHours(), m = d.getMinutes()
  var ampm = h < 12 ? "am" : "pm"
  h = h % 12 || 12
  return h + ":" + (m < 10 ? "0" : "") + m + " " + ampm
}

var DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

function when(epoch, now) {
  if (!epoch) return ""
  var d = new Date(epoch * 1000)
  now = now || new Date()
  var today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  var day = new Date(d.getFullYear(), d.getMonth(), d.getDate())
  var days = Math.round((today - day) / 86400000)
  if (days === 0) return "today " + clock(d)
  if (days === 1) return "yesterday " + clock(d)
  if (days < 7) return DAYS[d.getDay()] + " " + clock(d)
  var text = DAYS[d.getDay()].slice(0, 3) + " " + d.getDate() + " " + MONTHS[d.getMonth()]
  return d.getFullYear() === now.getFullYear() ? text : text + " " + d.getFullYear()
}

function capital(text) { return text ? text.charAt(0).toUpperCase() + text.slice(1) : "" }

function human(bytes) {
  if (bytes === null || bytes === undefined) return ""
  var units = ["bytes", "KB", "MB", "GB", "TB"], i = 0, n = bytes
  while (n >= 1000 && i < units.length - 1) { n /= 1000; i++ }
  return i === 0 ? n + " bytes" : n.toFixed(n < 10 ? 1 : 0) + " " + units[i]
}

function where(header) {
  if (!header) return ""
  if (header.kind === "disk") return "To your backup disk" + (header.model ? ", " + header.model : "")
  return "To your backup server" + (header.address ? " at " + header.address : "")
}

function free(header) {
  var n = header && header.space && header.space.free
  return n ? human(n) + " free" : ""
}

// What a running backup is doing, in words.
var STEPS = { starting: "Starting the backup", unlock: "Opening your backup", check: "Checking what changed", send: "Backing up",
              audit: "Noting your changes to Omarchy", point: "Making the restore point" }

function doing(running) {
  if (!running) return ""
  if (running.stopping) return "Stopping…"
  if (running.step === "check" && running.part) return "Checking " + running.part + "…"
  if (running.step === "clear" && running.part) return "Clearing removed and skipped files from " + running.part + "…"
  var text = STEPS[running.step] || "Backing up"
  text = running.part ? text + " " + running.part + "…" : text + "…"
  if (running.step === "send" && running.parts > 1) text += "  (part " + running.part_no + " of " + running.parts + ")"
  return text
}

// D49: the honest numbers under the bar. Time left only once the backup
// says it can be trusted (it sends null until then).
function rounded(seconds) {
  if (seconds === null || seconds === undefined) return ""
  if (seconds < 60) return "less than a minute"
  var minutes = seconds / 60
  if (minutes < 10) return "about " + Math.round(minutes) + " min"
  if (minutes < 60) return "about " + Math.round(minutes / 5) * 5 + " min"
  var step = minutes >= 120 ? 10 : 5
  var whole = Math.round(minutes / step) * step
  var h = Math.floor(whole / 60), m = whole % 60
  return "about " + h + " h" + (m ? " " + m + " min" : "")
}

function detail(running) {
  if (!running || running.step !== "send" || !running.total) return ""
  var bits = [(running.percent || 0) + "%", human(running.sent || 0) + " of " + human(running.total)]
  if (running.speed) bits.push(human(running.speed) + "/s")
  var left = rounded(running.left)
  if (left) bits.push(left + " left")
  return bits.join(" · ")
}

function already(running) {
  if (!running || running.step !== "send" || !running.already) return ""
  return human(running.already) + " was already on your backup"
}

function quiet(running) {
  if (!running || running.step !== "send" || !running.total || (running.quiet || 0) < 60) return ""
  var minutes = Math.floor(running.quiet / 60)
  return "Nothing has moved for " + minutes + (minutes === 1 ? " minute" : " minutes")
         + ". It stops at 3 if nothing changes."
}
