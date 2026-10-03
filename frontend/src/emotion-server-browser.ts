/**
 * LeafyGreen's Emotion entry initializes @emotion/server even in browser builds.
 * This client-only Vite app never calls server rendering APIs. Avoid importing
 * their Node stream dependencies into the browser; CSS insertion stays handled
 * by LeafyGreen's unmodified @emotion/css instance.
 */
export default function createEmotionServer() {
  const serverOnly = () => {
    throw new Error("Emotion server rendering is unavailable in the browser.");
  };
  return {
    extractCritical: serverOnly,
    renderStylesToString: serverOnly,
    renderStylesToNodeStream: serverOnly,
  };
}
