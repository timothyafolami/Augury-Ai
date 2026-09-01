/** Getting a long document out of a scrolling application.
 *
 * The report sheet lives inside the review column, and that column is
 * `lg:h-screen` with `overflow-y: auto` -- 855 pixels of scroll port around
 * 7176 pixels of document. Printing it in place gives you page one and
 * nothing else, because an ancestor that scrolls clips its contents in paged
 * media exactly as it does on screen. Repositioning the sheet does not escape
 * that either: an absolutely positioned box is still clipped by a scrolling
 * ancestor.
 *
 * So the sheet is lifted out. A clone is attached directly to `<body>` for
 * the duration of the print and removed afterwards, which leaves it with no
 * ancestor that can clip it and no layout to fight. The cost is that the
 * printed copy is a snapshot rather than the live node, which for a document
 * that does not change while you print it is not a cost.
 */

export const PRINT_ROOT = "augury-print-root";
export const PRINTING = "is-printing";

/** Put a printable copy of `sheet` directly on the body.
 *
 * Returns the function that undoes it. Idempotent: calling it twice does not
 * leave two copies, because both the browser's own print command and the
 * button can trigger it and a doubled document is worse than none.
 */
export function mountForPrint(sheet: Element, doc: Document = document): () => void {
  release(doc);

  const holder = doc.createElement("div");
  holder.id = PRINT_ROOT;
  holder.appendChild(sheet.cloneNode(true));
  doc.body.appendChild(holder);
  doc.documentElement.classList.add(PRINTING);

  return () => release(doc);
}

/** Remove the copy and the flag, whether or not one was ever added. */
export function release(doc: Document = document): void {
  doc.getElementById(PRINT_ROOT)?.remove();
  doc.documentElement.classList.remove(PRINTING);
}

/** Keep the browser's own print command working too.
 *
 * Someone who presses the shortcut expects the same document the button
 * produces. Wiring `beforeprint` means there is one printed artefact rather
 * than a good one and a broken one.
 */
export function watchPrinting(find: () => Element | null, win: Window = window): () => void {
  const before = () => {
    const sheet = find();
    if (sheet) mountForPrint(sheet, win.document);
  };
  const after = () => release(win.document);

  win.addEventListener("beforeprint", before);
  win.addEventListener("afterprint", after);

  return () => {
    win.removeEventListener("beforeprint", before);
    win.removeEventListener("afterprint", after);
    release(win.document);
  };
}
