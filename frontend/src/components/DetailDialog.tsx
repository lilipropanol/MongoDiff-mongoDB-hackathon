import type { ReactNode } from "react";
import Modal from "@leafygreen-ui/modal";

export function DetailDialog({
  title,
  children,
  onClose,
  compact = false,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  compact?: boolean;
}) {
  return (
    <Modal
      open
      setOpen={(open) => {
        if (!open) onClose();
      }}
      size={compact ? "default" : "large"}
      className="detail-modal"
      aria-labelledby="detail-title"
    >
      <h2 id="detail-title" className="detail-modal-title">
        {title}
      </h2>
      <div className="detail-modal-body">{children}</div>
    </Modal>
  );
}
