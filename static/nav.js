// Single source of truth for the nav bar (see trip-planning/static/nav.js,
// the app this pattern is generalized from) - change a link here once
// instead of hunting down every page's copy. Needs Global.buildNav
// (theme.js) and applyIcons (icons.js) already loaded.

// An individual list's page (/list.html?id=N) counts as part of "Lists".
const onListsPage = location.pathname === "/" || location.pathname === "/list.html";

Global.buildNav([
  { href: "/", icon: "list", label: "Lists", active: onListsPage },
  { href: "/contacts.html", icon: "person", label: "Contacts", active: location.pathname === "/contacts.html" },
  { href: "/categories.html", icon: "tag", label: "Categories", active: location.pathname === "/categories.html" },
  { icon: "refresh", label: "Refresh", onclick: () => location.reload() },
]);

// Everyone gets the Invites page (to ask for someone to be let in); the administrator
// also sees how many requests are waiting for them (the badge is kept current by
// invites.js).
Global.currentUser().then((me) => {
  const nav = document.querySelector(".app-nav");
  if (!me || !nav) return;
  const waiting = me.is_admin ? me.pending_invites || 0 : 0;
  const content = [Global.el("span", { class: "app-nav-icon", "data-icon": "settings", "aria-hidden": "true" }), "Invites"];
  if (me.is_admin) {
    content.push(
      Global.el("span", {
        id: "nav-invite-count",
        class: "item-badge item-badge-accent nav-count" + (waiting ? "" : " hidden"),
        text: String(waiting),
      })
    );
  }
  const link = Global.el(
    "a",
    { href: "/invites.html", class: "app-nav-link" + (location.pathname === "/invites.html" ? " active" : "") },
    content
  );
  nav.insertBefore(link, nav.lastElementChild); // ahead of Refresh, which stays last
  applyIcons(link);

  // The administrator also manages who has access (users.html).
  if (me.is_admin) {
    const users = Global.el(
      "a",
      { href: "/users.html", class: "app-nav-link" + (location.pathname === "/users.html" ? " active" : "") },
      [Global.el("span", { class: "app-nav-icon", "data-icon": "person", "aria-hidden": "true" }), "Users"]
    );
    nav.insertBefore(users, nav.lastElementChild);
    applyIcons(users);
  }
});

// Who's signed in, with a Log out link, in the page header (shared-assets).
Global.mountUserBadge();
