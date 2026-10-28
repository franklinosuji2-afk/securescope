import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "../auth";
import { initFloatingCards } from "../floating";
import LegalPage from "../pages/Legal";
import { CornerThemeToggle } from "../components/ThemeToggle";

function mockHover(matches: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockImplementation((query: string) => ({
      matches,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
    })),
  );
}

describe("floating cards", () => {
  let stop: () => void = () => undefined;
  beforeEach(() => {
    vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => {
      cb(0);
      return 1;
    });
    document.body.innerHTML = `<div class="landing"><div id="c" class="card"><span id="inner">x</span></div><p id="o">y</p></div>`;
    const card = document.getElementById("c") as HTMLElement;
    card.getBoundingClientRect = () =>
      ({
        left: 100,
        top: 100,
        width: 200,
        height: 100,
        right: 300,
        bottom: 200,
        x: 100,
        y: 100,
        toJSON: () => ({}),
      }) as DOMRect;
  });
  afterEach(() => {
    stop();
    vi.unstubAllGlobals();
  });

  it("publishes the pointer position and a small tilt on the card under the mouse", () => {
    mockHover(true);
    stop = initFloatingCards();
    fireEvent.pointerMove(document.getElementById("inner") as HTMLElement, {
      clientX: 300,
      clientY: 100,
      pointerType: "mouse",
    });
    const card = document.getElementById("c") as HTMLElement;
    expect(card.style.getPropertyValue("--px")).toBe("100.0%");
    expect(card.style.getPropertyValue("--py")).toBe("0.0%");
    expect(card.style.getPropertyValue("--rx")).toBe("2.50deg");
    expect(card.style.getPropertyValue("--ry")).toBe("2.50deg");
  });

  it("clears the tilt when the pointer leaves the card", () => {
    mockHover(true);
    stop = initFloatingCards();
    fireEvent.pointerMove(document.getElementById("c") as HTMLElement, {
      clientX: 200,
      clientY: 150,
      pointerType: "mouse",
    });
    const card = document.getElementById("c") as HTMLElement;
    expect(card.style.getPropertyValue("--rx")).toBe("0.00deg");
    fireEvent.mouseOut(card, { relatedTarget: document.getElementById("o") });
    expect(card.style.getPropertyValue("--rx")).toBe("");
  });

  it("ignores touch and does nothing on devices that cannot hover", () => {
    mockHover(true);
    stop = initFloatingCards();
    const card = document.getElementById("c") as HTMLElement;
    fireEvent.pointerMove(card, {
      clientX: 200,
      clientY: 150,
      pointerType: "touch",
    });
    expect(card.style.getPropertyValue("--px")).toBe("");
    stop();
    mockHover(false);
    stop = initFloatingCards();
    fireEvent.pointerMove(card, {
      clientX: 200,
      clientY: 150,
      pointerType: "mouse",
    });
    expect(card.style.getPropertyValue("--px")).toBe("");
  });
});

describe("theme toggle on pages without a header", () => {
  it("is on the legal pages and switches the theme", () => {
    render(
      <AuthProvider>
        <LegalPage page="privacy" />
      </AuthProvider>,
    );
    const toggle = screen.getByRole("button", {
      name: /Switch to (light|dark) theme/,
    });
    const before = document.documentElement.getAttribute("data-theme");
    fireEvent.click(toggle);
    expect(document.documentElement.getAttribute("data-theme")).not.toBe(
      before,
    );
  });

  it("the corner toggle is a single labelled button", () => {
    render(<CornerThemeToggle />);
    expect(
      screen.getAllByRole("button", { name: /Switch to (light|dark) theme/ }),
    ).toHaveLength(1);
  });
});
