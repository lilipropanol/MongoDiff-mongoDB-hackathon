import { useState } from "react";
import Code from "@leafygreen-ui/code";
import Icon from "@leafygreen-ui/icon";
import IconButton from "@leafygreen-ui/icon-button";
import { download } from "../api";
export function CodeBlock({
  code,
  filename,
  label,
}: {
  code: string;
  filename: string;
  label: string;
}) {
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");
  async function copy() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setError("");
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setError("Copy is unavailable. Download the file instead.");
    }
  }
  return (
    <div className="code-panel">
      <div className="code-toolbar">
        <span>
          <Icon aria-hidden glyph="Code" />
          {label}
        </span>
        <div className="button-group">
          <IconButton
            onClick={copy}
            aria-label={copied ? "Copied code" : "Copy code"}
          >
            <Icon aria-hidden glyph={copied ? "Checkmark" : "Copy"} />
          </IconButton>
          <IconButton
            onClick={() => download(filename, code, "text/plain")}
            aria-label={`Download ${filename}`}
          >
            <Icon aria-hidden glyph="Download" />
          </IconButton>
        </div>
      </div>
      <div className="code-scroll" tabIndex={0} aria-label={label}>
        <Code
          language={
            filename.endsWith(".py")
              ? "python"
              : filename.endsWith(".js")
                ? "javascript"
                : "json"
          }
          copyButtonAppearance="none"
          showLineNumbers
        >
          {code}
        </Code>
      </div>
      {error && (
        <p role="status" className="code-message">
          {error}
        </p>
      )}
    </div>
  );
}
