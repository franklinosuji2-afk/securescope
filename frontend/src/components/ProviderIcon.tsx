import type { OAuthProvider } from "../api";
import githubMark from "../assets/provider-github.png";
import googleMark from "../assets/provider-google.png";

/**
 * The providers' own marks for the sign-in buttons. The Google "G" keeps its colours. The GitHub mark is used
 * as a mask, so it takes the button's text colour and reads in both themes. Both are decorative: the button
 * text names the action.
 */
export default function ProviderIcon({
  provider,
}: {
  provider: OAuthProvider;
}) {
  if (provider === "google") {
    return (
      <img
        className="provider-icon"
        src={googleMark}
        alt=""
        width="20"
        height="20"
        aria-hidden="true"
      />
    );
  }
  return (
    <span
      className="provider-icon provider-icon-mask"
      style={{
        maskImage: `url(${githubMark})`,
        WebkitMaskImage: `url(${githubMark})`,
      }}
      aria-hidden="true"
    />
  );
}
