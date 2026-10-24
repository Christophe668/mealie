import type { Icon } from "~/lib/icons/icon-type";

export interface SideBarLink {
  key?: string;
  icon: string;
  to?: string;
  href?: string;
  title: string;
  children?: SideBarLink[];
  childrenStartExpanded?: boolean;
  restricted: boolean;
}

export type SidebarLinks = Array<SideBarLink>;

/** A destination in the app shell's rail or tab bar. `active` drives aria-current="page". */
export interface AppShellNavItem {
  key: string;
  label: string;
  to: string;
  icon: keyof Icon;
  active: boolean;
}

/** An entry in an app shell menu (add menu, user menu): a link (`to`) or an action (`onSelect`). */
export interface AppShellMenuItem {
  key: string;
  label: string;
  icon: keyof Icon;
  to?: string;
  onSelect?: () => void;
  /** Set (true or false) to render a menuitemradio, e.g. the theme choice. */
  checked?: boolean;
  /** Draws a hairline above the item to start a new group. */
  dividerBefore?: boolean;
}
