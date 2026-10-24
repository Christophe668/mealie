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
