// Single source of truth for the nav bar (see trip-planning/static/nav.js,
// the app this pattern is generalized from) - change a link here once
// instead of hunting down every page's copy. Needs Global.buildNav
// (theme.js) and applyIcons (icons.js) already loaded.

Global.buildNav([
  { href: "/", icon: "gift", label: "Gifts", active: location.pathname === "/" },
  { href: "/contacts.html", icon: "person", label: "Contacts", active: location.pathname === "/contacts.html" },
  { icon: "refresh", label: "Refresh", onclick: () => location.reload() },
]);
