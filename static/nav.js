// Single source of truth for the nav bar (see trip-planning/static/nav.js,
// the app this pattern is generalized from) - change a link here once
// instead of hunting down every page's copy. Needs Global.buildNav
// (theme.js) and applyIcons (icons.js) already loaded.

// An individual list's page (/list.html?id=N) counts as part of "Lists".
const onListsPage = location.pathname === "/" || location.pathname === "/list.html";
const here = (path) => location.pathname === path;

// The nav is built straight away, then rebuilt once we know who is signed in:
// everyone gets Invites (to ask for someone to be let in); the administrator
// also sees how many requests are waiting (kept current by invites.js) and
// gets the Users page. Groups only show in the sidebar layout.
function buildListsNav(me) {
  const admin = !!(me && me.is_admin);
  const items = [
    { href: "/", icon: "list", label: "Lists", active: onListsPage },
    { href: "/contacts.html", icon: "person", label: "Contacts", active: here("/contacts.html") },
    { href: "/categories.html", icon: "tag", label: "Categories", active: here("/categories.html"), group: "Setup" },
    { href: "/link-labels.html", icon: "sliders", label: "Link labels", active: here("/link-labels.html"), group: "Setup" },
  ];
  if (me) {
    items.push({
      href: "/invites.html",
      icon: "settings",
      label: "Invites",
      active: here("/invites.html"),
      group: "Access",
      badge: admin ? { id: "nav-invite-count", count: me.pending_invites || 0 } : null,
    });
  }
  if (admin) items.push({ href: "/users.html", icon: "person", label: "Users", active: here("/users.html"), group: "Access" });
  items.push({ icon: "refresh", label: "Refresh", onclick: () => location.reload() });
  Global.buildNav(items);
}

buildListsNav(null);
Global.currentUser().then((me) => {
  if (me) buildListsNav(me);
});

// Who's signed in, with a Log out link, in the page header (shared-assets).
Global.mountUserBadge();
