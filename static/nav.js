// Single source of truth for the nav bar (see trip-planning/static/nav.js,
// the app this pattern is generalized from) - change a link here once
// instead of hunting down every page's copy. Needs Global.buildNav
// (theme.js) and applyIcons (icons.js) already loaded.

// An individual list's page (/list.html?id=N) counts as part of "Lists".
const onListsPage = location.pathname === "/" || location.pathname === "/list.html";

Global.buildNav([
  { href: "/", icon: "list", label: "Lists", active: onListsPage },
  { href: "/contacts.html", icon: "person", label: "Contacts", active: location.pathname === "/contacts.html" },
  { icon: "refresh", label: "Refresh", onclick: () => location.reload() },
]);
