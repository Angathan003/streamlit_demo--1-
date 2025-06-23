import streamlit as st
import fitz
import os
import re
import csv
import shutil
import urllib.parse
import tempfile
import zipfile
from pathlib import Path
from io import BytesIO

# --- Extraction Helpers ---

def slugify(s: str, maxlen: int = 50) -> str:
    s = s.lower()
    s = re.sub(r'[^\w\s-]', '', s)
    s = re.sub(r'[\s_-]+', '_', s)
    return s.strip('_')[:maxlen] or "article"

def find_heading(blocks, page_height,
                 size_thresh: float = 18,
                 y_margin_frac: float = 0.15,
                 min_chars: int = 10) -> str:
    y_limit = page_height * y_margin_frac
    for blk in blocks:
        if blk.get("type") != 0:
            continue
        _, y0, _, _ = blk.get("bbox", [0,0,0,0])
        if y0 > y_limit:
            continue
        spans = [span for line in blk["lines"] for span in line["spans"]]
        if not spans or max(span["size"] for span in spans) < size_thresh:
            continue
        text = " ".join(span["text"].strip() for span in spans)
        text = re.sub(r'\s+', ' ', text).strip()
        if len(text) >= min_chars:
            return text
    return None

def extract_to_markdown(pdf_path: Path, out_dir: Path):
    """
    Extracts articles by heading, writes:
      - output.csv
      - images_out/
      - articles/*.md
    into out_dir.
    """
    doc = fitz.open(str(pdf_path))
    articles = []
    current = dict(id=1, title=None, start_page=None,
                   end_page=None, paragraphs=[])

    img_root = out_dir / "images_out"
    md_root = out_dir / "articles"
    csv_path = out_dir / "output.csv"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    img_root.mkdir(parents=True)
    md_root.mkdir(parents=True)

    # Walk pages
    for pageno, page in enumerate(doc, start=1):
        blocks = page.get_text("dict")["blocks"]
        heading = find_heading(blocks, page.rect.height)
        if heading:
            if current["title"] is not None:
                current["end_page"] = pageno - 1
                articles.append(current)
                current = dict(id=current["id"]+1,
                               title=None,
                               start_page=None,
                               end_page=None,
                               paragraphs=[])
            current["title"] = heading
            current["start_page"] = pageno

        if current["title"] is None:
            current["title"] = f"article_{current['id']}"
            current["start_page"] = 1

        # Text → paragraphs
        page_text = page.get_text().strip()
        paras = [p for p in page_text.split("\n\n") if p.strip()]
        for p in paras:
            current["paragraphs"].append(dict(text=p, images=[]))

        # Images
        img_list = page.get_images(full=True)
        if img_list and current["paragraphs"]:
            art_folder = img_root / f"{current['id']:03d}_{slugify(current['title'])}"
            art_folder.mkdir(parents=True, exist_ok=True)
            for idx, imginfo in enumerate(img_list, start=1):
                xref = imginfo[0]
                pix = fitz.Pixmap(doc, xref)
                ext = "png" if pix.alpha else "jpg"
                img_path = art_folder / f"p{pageno:03d}_i{idx}.{ext}"
                pix.save(str(img_path)); pix = None
                current["paragraphs"][-1]["images"].append(str(img_path))

    # Finalize
    if current["title"] is not None:
        current["end_page"] = doc.page_count
        articles.append(current)

    # CSV summary
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id","title","start_page","end_page","image_count"])
        for art in articles:
            img_count = sum(len(p["images"]) for p in art["paragraphs"])
            writer.writerow([
                art["id"], art["title"],
                art["start_page"], art["end_page"], img_count
            ])

    # Write MD files
    for art in articles:
        fname = f"{art['id']:03d}_{slugify(art['title'])}.md"
        md_file = md_root / fname
        with open(md_file, "w", encoding="utf-8") as md:
            md.write(f"# {art['title']}\n\n")
            for para in art["paragraphs"]:
                md.write(para["text"] + "\n\n")
                for img in para["images"]:
                    rel = os.path.relpath(img, start=md_root)
                    rel = rel.replace("\n", "").replace("\\", "/")
                    url = urllib.parse.quote(rel)
                    md.write(f"![{Path(img).name}]({url})\n\n")

    return {"out_dir": out_dir, "articles": articles}

# --- Streamlit App ---

def main():
    st.title("📄 Jaffna monitor  PDF Article Extractor")

    uploaded = st.file_uploader(
        "Upload one or more PDFs",
        type=["pdf"], accept_multiple_files=True
    )

    if not uploaded:
        st.info("Please upload at least one PDF to begin.")
        return

    if st.button("Extract Articles"):
        with st.spinner("Processing PDFs…"):
            # Use a temp dir to hold files
            tmp = Path(tempfile.mkdtemp())
            results = []
            for pdf_file in uploaded:
                pdf_path = tmp / pdf_file.name
                with open(pdf_path, "wb") as f:
                    f.write(pdf_file.getbuffer())
                # FIX: Use Path(pdf_file.name).stem to get filename stem
                out_dir = tmp / slugify(Path(pdf_file.name).stem)
                res = extract_to_markdown(pdf_path, out_dir)
                results.append(res)

        # Display results
        for res in results:
            base = res["out_dir"]
            st.subheader(f"📂 {base.name}")
            # Show summary table
            df = []
            for art in res["articles"]:
                df.append({
                    "ID": art["id"],
                    "Title": art["title"],
                    "Pages": f"{art['start_page']}–{art['end_page']}",
                    "Images": sum(len(p["images"]) for p in art["paragraphs"])
                })
            st.table(df)

            # Preview articles
            for art in res["articles"]:
                key = f"{base.name}_{art['id']}"
                with st.expander(f"{art['id']:03d} {art['title']}", expanded=False):
                    md_path = base / "articles" / f"{art['id']:03d}_{slugify(art['title'])}.md"
                    content = md_path.read_text(encoding="utf-8")
                    st.markdown(content, unsafe_allow_html=True)

                    # Download individual MD
                    st.download_button(
                        label="Download this article (MD)",
                        data=content,
                        file_name=md_path.name,
                        mime="text/markdown",
                        key=key + "_dl"
                    )

            # Bulk download as ZIP
            zip_buf = BytesIO()
            with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zipf:
                for folder, _, files in os.walk(base):
                    for fn in files:
                        file_path = Path(folder) / fn
                        arcname = file_path.relative_to(base)
                        zipf.write(file_path, arcname)
            zip_buf.seek(0)
            st.download_button(
                label="⬇️ Download all output as ZIP",
                data=zip_buf,
                file_name=f"{base.name}_extracted.zip",
                mime="application/zip",
                key=base.name + "_zip"
            )

if __name__ == "__main__":
    main()
