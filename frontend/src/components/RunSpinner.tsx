import { useEffect, useRef, useState } from "react";
import { LoaderCircle } from "lucide-react";
import { cn } from "@/lib/utils";

const watched = new Map<Element, (visible: boolean) => void>();
let observer: IntersectionObserver | undefined;

/** A single observer keeps offscreen history rows from animating. No frame loop. */
function watch(element: Element, onVisible: (visible: boolean) => void) {
  observer ??= new IntersectionObserver((entries) => {
    for (const entry of entries)
      watched.get(entry.target)?.(
        entry.isIntersecting && entry.intersectionRatio > 0,
      );
  });
  watched.set(element, onVisible);
  observer.observe(element);
  return () => {
    observer?.unobserve(element);
    watched.delete(element);
    if (!watched.size) {
      observer?.disconnect();
      observer = undefined;
    }
  };
}

export function RunSpinner({
  active = true,
  size = 14,
}: {
  active?: boolean;
  size?: number;
}) {
  const element = useRef<HTMLSpanElement>(null);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    if (!active || !element.current) return;
    return watch(element.current, setVisible);
  }, [active]);
  return (
    <span ref={element} className="inline-flex shrink-0" aria-hidden="true">
      <LoaderCircle
        size={size}
        data-animate={active && visible}
        className={cn(
          "run-spinner",
          active ? "text-add" : "text-muted-foreground",
        )}
      />
    </span>
  );
}
