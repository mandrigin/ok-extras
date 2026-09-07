function entries(usage) {
  var apps = usage.app_definitions || {}
  var groups = usage.budgets || {}
  var seen = Object.create(null)
  return (usage.enabled_apps || []).filter(function(id) { return !!apps[id] }).map(function(id) {
    var app = apps[id], key = app.budget || ("app:" + id)
    if (seen[key]) return null
    seen[key] = true
    var budget = groups[app.budget]
    return {app: id, title: budget ? budget.label : app.label,
            remaining: budget ? budget.remaining_seconds : null}
  }).filter(function(entry) { return entry !== null })
}
