"use client";

import type { MenuGroup as MenuGroupModel, MenuItemModel } from "@/components/card/cardActions";
import { MenuItem } from "./MenuItem";
import { Submenu } from "./Submenu";

export interface MenuGroupProps {
  group: MenuGroupModel;
  first: boolean;
  onActivate: (item: MenuItemModel) => void;
  openSubmenuId: string | null;
  setOpenSubmenuId: (id: string | null) => void;
  onCloseAll: (reason: "escape" | "tab" | "select" | "outside") => void;
}

export function MenuGroup({ group, first, onActivate, openSubmenuId, setOpenSubmenuId, onCloseAll }: MenuGroupProps) {
  return (
    <>
      {!first && <div role="separator" className="dd-menu-sep" />}
      <div role="group" data-group-id={group.id}>
        {group.items.map((item) =>
          item.submenu ? (
            <Submenu
              key={item.id}
              item={item}
              open={openSubmenuId === item.id}
              onOpen={() => setOpenSubmenuId(item.id)}
              onClose={() => setOpenSubmenuId(null)}
              onActivate={onActivate}
              onCloseAll={onCloseAll}
            />
          ) : (
            <MenuItem key={item.id} item={item} onActivate={onActivate} onPointerEnter={() => setOpenSubmenuId(null)} />
          ),
        )}
      </div>
    </>
  );
}
