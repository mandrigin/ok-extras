// Pure functions shared by the AppLibrary adapter and launcher regression tests.
function normalize(id) {
  var value = String(id || "")
  return value.slice(-8) === ".desktop" ? value.slice(0, -8) : value
}

function permits(manifest, user, desktopId) {
  if (!manifest || manifest.user !== user) return true
  var ids = Array.isArray(manifest.desktop_ids) ? manifest.desktop_ids : []
  return ids.indexOf(normalize(desktopId)) !== -1
}
