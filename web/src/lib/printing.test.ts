// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { PRINTING, PRINT_ROOT, mountForPrint, release, watchPrinting } from "./printing";

/** The document has to escape the application's layout to print.
 *
 * Measured on the running interface: the sheet is 7176px tall and sits inside
 * a column that is 855px with `overflow-y: auto`. Printed in place it is one
 * page and a shrug. Every test here is about the sheet ending up somewhere
 * nothing can clip it, and about not leaving that copy behind afterwards.
 */

const sheetOf = (text = "one finding") => {
  document.body.innerHTML = `
    <div id="app" style="overflow-y:auto">
      <article class="sheet"><p>${text}</p></article>
    </div>`;
  return document.querySelector(".sheet") as Element;
};

/** Watchers attach to the one shared window, so a test that leaves one
 *  attached makes the next test pass or fail for the previous test's reasons.
 *  Found exactly that way: a "stops listening" test failed because two earlier
 *  cases were still listening. */
const attached: Array<() => void> = [];
const watch = (find: () => Element | null) => {
  const stop = watchPrinting(find);
  attached.push(stop);
  return stop;
};

beforeEach(() => {
  document.body.innerHTML = "";
  document.documentElement.className = "";
});

afterEach(() => {
  while (attached.length) attached.pop()?.();
});

describe("lifting the sheet out to print", () => {
  it("puts a copy directly on the body", () => {
    mountForPrint(sheetOf());

    const holder = document.getElementById(PRINT_ROOT);

    expect(holder).not.toBeNull();
    expect(holder?.parentElement).toBe(document.body);
  });

  it("copies the content rather than moving the original", () => {
    // Moving it would empty the page behind the print dialog, and a cancelled
    // print would leave the reader looking at nothing.
    const sheet = sheetOf("the pool is created per request");
    mountForPrint(sheet);

    expect(document.querySelectorAll(".sheet").length).toBe(2);
    expect(sheet.isConnected).toBe(true);
    expect(document.getElementById(PRINT_ROOT)?.textContent).toContain(
      "the pool is created per request",
    );
  });

  it("leaves nothing between the copy and the body", () => {
    // The whole point: no ancestor that scrolls, so nothing that clips.
    mountForPrint(sheetOf());

    const copy = document.getElementById(PRINT_ROOT)?.firstElementChild;
    const between: string[] = [];
    let node = copy?.parentElement;
    while (node && node !== document.body) {
      between.push(node.id || node.tagName);
      node = node.parentElement;
    }

    expect(between).toEqual([PRINT_ROOT]);
  });

  it("flags the document so the stylesheet can hide everything else", () => {
    mountForPrint(sheetOf());

    expect(document.documentElement.classList.contains(PRINTING)).toBe(true);
  });

  it("does not stack a second copy when called twice", () => {
    // Both the button and the browser's own print command reach this, and two
    // copies is a two-times-longer document.
    const sheet = sheetOf();
    mountForPrint(sheet);
    mountForPrint(sheet);

    expect(document.querySelectorAll(`#${PRINT_ROOT}`).length).toBe(1);
    expect(document.querySelectorAll(".sheet").length).toBe(2);
  });
});

describe("cleaning up", () => {
  it("removes the copy and the flag", () => {
    const undo = mountForPrint(sheetOf());
    undo();

    expect(document.getElementById(PRINT_ROOT)).toBeNull();
    expect(document.documentElement.classList.contains(PRINTING)).toBe(false);
    expect(document.querySelectorAll(".sheet").length).toBe(1);
  });

  it("is safe when nothing was ever mounted", () => {
    expect(() => release()).not.toThrow();
  });
});

describe("the browser's own print command", () => {
  it("gets the same document the button produces", () => {
    sheetOf();
    watch(() => document.querySelector(".sheet"));

    window.dispatchEvent(new Event("beforeprint"));

    expect(document.getElementById(PRINT_ROOT)).not.toBeNull();
  });

  it("cleans up when the print finishes", () => {
    sheetOf();
    watch(() => document.querySelector(".sheet"));

    window.dispatchEvent(new Event("beforeprint"));
    window.dispatchEvent(new Event("afterprint"));

    expect(document.getElementById(PRINT_ROOT)).toBeNull();
  });

  it("stops listening when the component goes away", () => {
    sheetOf();
    const stop = watch(() => document.querySelector(".sheet"));
    stop();

    window.dispatchEvent(new Event("beforeprint"));

    expect(document.getElementById(PRINT_ROOT)).toBeNull();
  });

  it("does nothing when there is no report on screen", () => {
    document.body.innerHTML = "<p>no review yet</p>";
    watch(() => document.querySelector(".sheet"));

    window.dispatchEvent(new Event("beforeprint"));

    expect(document.getElementById(PRINT_ROOT)).toBeNull();
  });
});
