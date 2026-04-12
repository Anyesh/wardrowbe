"use client";
import Lightbox from "yet-another-react-lightbox";
import Zoom from "yet-another-react-lightbox/plugins/zoom";
import Captions from "yet-another-react-lightbox/plugins/captions";
import Counter from "yet-another-react-lightbox/plugins/counter";
import "yet-another-react-lightbox/styles.css";
import "yet-another-react-lightbox/plugins/captions.css";
import "yet-another-react-lightbox/plugins/counter.css";
import Link from "next/link";
import { Shirt, ChevronRight } from "lucide-react";
import { useLightbox } from "@/lib/lightbox-context";

export function ImageLightbox() {
  const { visible, images, index, currentItemId, close, setIndex } = useLightbox();

  const slides = images.map((img) => ({
    src: img.uri,
    alt: img.itemName ?? "",
    title: img.itemName,
    description: img.itemCategory,
  }));

  const safeIndex = Math.max(0, Math.min(index, images.length - 1));
  const current = images[safeIndex];
  const showChip = !!current?.itemId && current.itemId !== currentItemId;

  return (
    <Lightbox
      open={visible}
      close={close}
      index={safeIndex}
      slides={slides}
      on={{
        view: ({ index: newIndex }: { index: number }) => setIndex(newIndex),
      }}
      plugins={[Zoom, Captions, Counter]}
      zoom={{ maxZoomPixelRatio: 4, doubleTapDelay: 250, doubleClickDelay: 250 }}
      counter={{ container: { style: { top: 16 } } }}
      styles={{
        root: { pointerEvents: "auto" },
        container: { backgroundColor: "rgba(0, 0, 0, 0.95)" },
      }}
      toolbar={{
        buttons: [
          showChip && current?.itemId ? (
            <Link
              key="open-in-wardrobe"
              href={`/dashboard/wardrobe?item=${current.itemId}`}
              onClick={close}
              className="yarl__button"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                padding: "8px 14px",
                marginRight: 8,
                backgroundColor: "rgba(255,255,255,0.95)",
                color: "#000",
                borderRadius: 999,
                fontSize: 13,
                fontWeight: 600,
                textDecoration: "none",
              }}
            >
              <Shirt size={16} />
              Open in Wardrobe
              <ChevronRight size={16} />
            </Link>
          ) : null,
          "close",
        ].filter(Boolean) as React.ReactNode[],
      }}
    />
  );
}
