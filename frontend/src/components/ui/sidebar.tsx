import { createContext, useCallback, useContext, useEffect, useRef, useState, type ComponentProps, type ReactNode } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { PanelLeft, X } from "lucide-react";
import type { PanelImperativeHandle } from "react-resizable-panels";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { cn } from "@/lib/utils";
import { Button } from "./button";
import { ResizableHandle, ResizablePanel } from "./resizable";

type SidebarContextValue = {
  open: boolean;
  setOpen: (value: boolean) => void;
  openMobile: boolean;
  setOpenMobile: (value: boolean) => void;
  isMobile: boolean;
  toggleSidebar: () => void;
};
const SidebarContext = createContext<SidebarContextValue | null>(null);

export function useSidebar() {
  const value = useContext(SidebarContext);
  if (!value) throw new Error("useSidebar requires SidebarProvider");
  return value;
}

// Adapted to CCS from shadcn/ui's provider / sidebar / inset / menu composition.
// Desktop uses a resizable panel; mobile uses Radix's focus-trapped sheet.
export function SidebarProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(() => localStorage.getItem("ccsweb.sidebar.open") !== "false");
  const [openMobile, setOpenMobile] = useState(false);
  const isMobile = useMediaQuery("(max-width: 679px)");
  const toggleSidebar = useCallback(() => {
    if (isMobile) setOpenMobile(value => !value);
    else setOpen(value => !value);
  }, [isMobile]);

  useEffect(() => { localStorage.setItem("ccsweb.sidebar.open", String(open)); }, [open]);
  useEffect(() => { if (!isMobile) setOpenMobile(false); }, [isMobile]);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "b") {
        event.preventDefault();
        toggleSidebar();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggleSidebar]);

  return (
    <SidebarContext.Provider value={{ open, setOpen, openMobile, setOpenMobile, isMobile, toggleSidebar }}>
      <div data-slot="sidebar-wrapper" className="flex h-full min-w-0 flex-col overflow-hidden">{children}</div>
    </SidebarContext.Provider>
  );
}

export function Sidebar({ children }: { children: ReactNode }) {
  const { open, isMobile, openMobile, setOpenMobile } = useSidebar();
  const panel = useRef<PanelImperativeHandle>(null);
  const [initialWidth] = useState(() => {
    const saved = Number(localStorage.getItem("ccsweb.sidebar.width"));
    return saved >= 230 && saved <= 440 ? saved : 288;
  });

  if (isMobile) {
    return (
      <Dialog.Root open={openMobile} onOpenChange={setOpenMobile}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-40 bg-black/55 backdrop-blur-[2px]" />
          <Dialog.Content aria-describedby={undefined} onCloseAutoFocus={event => { event.preventDefault(); document.querySelector<HTMLButtonElement>('[data-slot="sidebar-trigger"]')?.focus(); }} className="fixed inset-y-0 left-0 z-50 flex w-[min(330px,calc(100vw-40px))] flex-col border-r border-border bg-sidebar shadow-xl outline-none">
            <div className="flex h-12 shrink-0 items-center justify-between border-b border-border px-3">
              <Dialog.Title className="text-sm font-semibold">Chat history</Dialog.Title>
              <Dialog.Close asChild><Button size="icon" aria-label="Close history"><X size={16} /></Button></Dialog.Close>
            </div>
            <aside data-slot="sidebar" className="min-h-0 flex-1" aria-label="Chat history">{children}</aside>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    );
  }
  if (!open) return null;
  return (
    <>
      <ResizablePanel id="history-sidebar" panelRef={panel} defaultSize={initialWidth} minSize={230} maxSize="40%" groupResizeBehavior="preserve-pixel-size"
        onResize={(size, _id, previous) => {
          if (previous && size.inPixels >= 230) localStorage.setItem("ccsweb.sidebar.width", String(Math.round(size.inPixels)));
        }}>
        <aside data-slot="sidebar" aria-label="Chat history" className="flex h-full min-w-0 flex-col bg-sidebar text-sidebar-foreground">{children}</aside>
      </ResizablePanel>
      <ResizableHandle withHandle aria-label="Resize history sidebar" title="Drag to resize history. Double-click to reset."
        disableDoubleClick onDoubleClick={() => panel.current?.resize(288)} />
    </>
  );
}

export function SidebarTrigger() {
  const { open, openMobile, isMobile, toggleSidebar } = useSidebar();
  return <Button data-slot="sidebar-trigger" size="icon" onClick={toggleSidebar} aria-label="Toggle history sidebar" aria-expanded={isMobile ? openMobile : open} title="Toggle history (Ctrl+B)"><PanelLeft size={17} /></Button>;
}

export function SidebarHeader({ className, ...props }: ComponentProps<"div">) {
  return <div data-slot="sidebar-header" className={cn("flex shrink-0 flex-col gap-3 p-3", className)} {...props} />;
}
export function SidebarContent({ className, ...props }: ComponentProps<"div">) {
  return <div data-slot="sidebar-content" className={cn("min-h-0 flex-1 overflow-y-auto", className)} {...props} />;
}
export function SidebarFooter({ className, ...props }: ComponentProps<"div">) {
  return <div data-slot="sidebar-footer" className={cn("shrink-0 border-t border-border p-3", className)} {...props} />;
}
export function SidebarInset({ className, ...props }: ComponentProps<"main">) {
  return <main data-slot="sidebar-inset" className={cn("flex h-full min-w-0 flex-col bg-background", className)} {...props} />;
}
export function SidebarMenu({ className, ...props }: ComponentProps<"ul">) {
  return <ul data-slot="sidebar-menu" className={cn("flex min-w-0 flex-col gap-1 px-2 pb-2", className)} {...props} />;
}
export function SidebarMenuItem(props: ComponentProps<"li">) {
  return <li data-slot="sidebar-menu-item" {...props} />;
}
export function SidebarMenuButton({ className, isActive, ...props }: ComponentProps<"button"> & { isActive?: boolean }) {
  return <button data-slot="sidebar-menu-button" data-active={isActive} aria-current={isActive ? "true" : undefined} type="button"
    className={cn("relative w-full overflow-hidden rounded-lg border border-transparent p-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring", className)} {...props} />;
}
