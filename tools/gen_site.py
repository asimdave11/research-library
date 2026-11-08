#!/usr/bin/env python3
"""Build the public research-library site from a JabRef library.bib.

Usage: gen_site.py <library.bib> <output_dir>

Writes README.md, sections/*.md, inbox/*.md, index.html and a public
library.bib (curated sections only; no abstracts, PDFs, notes or comments).
"""
import json, re, sys, os, html, datetime, collections
import bibtexparser
from bibtexparser.bparser import BibTexParser
from bibtexparser.bwriter import BibTexWriter
from bibtexparser.bibdatabase import BibDatabase

SRC, OUT = sys.argv[1], sys.argv[2]

# page slug -> (title, top-level group, [(subgroup name, label)], blurb)
SECTIONS = [
    ("must-read-popgen", "Must Read · Population genetics", "Must Read: Population genetics",
     [("Population genetics: Classics", "Classics"), ("Population genetics: Recent", "Recent")],
     "Foundational and recent papers in population genetics: neutral theory, coalescent, selection, demography, admixture, ancient DNA."),
    ("must-read-proteins", "Must Read · Proteins", "Must Read: Proteins", [],
     "Physical principles of proteins: hydrophobicity, electrostatics, folding, disorder, membranes, simulation."),
    ("must-read-immunology", "Must Read · Immunology", "Must Read: Immunology", [],
     "T cell biology, exhaustion and tumor immunology, plus foundational immunology."),
    ("popgen-protein", "popgen-protein", "popgen-protein", [],
     "Where protein biophysics meets population genetics: protein properties used to understand variation, selection and constraint."),
    ("brannigan-lab", "Brannigan Lab", "Brannigan Lab",
     [("Brannigan: Research articles", "Research articles"), ("Brannigan: Reviews", "Reviews"),
      ("Brannigan: Books & chapters", "Books & chapters"), ("Brannigan: Preprints", "Preprints")],
     "Grace Brannigan (first/last author) and Matthew E. B. Hansen (any position)."),
    ("schietinger-lab", "Schietinger Lab", "Schietinger Lab",
     [("Schietinger: Research articles", "Research articles"), ("Schietinger: Reviews", "Reviews"),
      ("Schietinger: Preprints", "Preprints")],
     "Andrea Schietinger as first or last author."),
    ("pezzuto-lab", "Pezzuto Lab", "Pezzuto Lab",
     [("Pezzuto: Research articles", "Research articles"), ("Pezzuto: Reviews", "Reviews"),
      ("Pezzuto: Books & chapters", "Books & chapters"), ("Pezzuto: Editorials & letters", "Editorials & letters")],
     "John M. Pezzuto as first or last author."),
]

def clean(s):
    s = re.sub(r'[{}]', '', s or '')
    s = s.replace('\\&', '&').replace('\\%', '%').replace('\\_', '_')
    return re.sub(r'\s+', ' ', s).strip()

def authors_list(a):
    if not a:
        return []
    out = []
    for p in re.split(r'\s+and\s+', a):
        p = clean(p)
        if ',' in p:
            last, first = [x.strip() for x in p.split(',', 1)]
            ini = ''.join(w[0] for w in re.split(r'[\s\-.]+', first) if w)
            out.append((last + ' ' + ini).strip())
        else:
            out.append(p)
    return out

def short_authors(al):
    if not al:
        return ''
    if len(al) <= 3:
        return ', '.join(al)
    return f"{al[0]}, {al[1]} … {al[-1]}"

p = BibTexParser(common_strings=True)
p.ignore_nonstandard_types = False
db = bibtexparser.loads(open(SRC, encoding='utf-8').read(), p)

curated = {s[2] for s in SECTIONS}
inbox_re = re.compile(r'^(Inbox \d{4}-\d{2}-\d{2}|Labs \d{4}-\d{2})$')

records = []
public_entries = []
inbox = collections.defaultdict(list)
for e in db.entries:
    groups = [g.strip() for g in e.get('groups', '').split(',') if g.strip()]
    inb = [g for g in groups if inbox_re.match(g)]
    if not (set(groups) & curated) and not inb:
        continue  # personal / ungrouped entries stay private
    kw = e.get('keywords', '')
    title = clean(e.get('title', '')).rstrip('.')
    al = authors_list(e.get('author') or e.get('editor', ''))
    doi = e.get('doi', '').strip()
    pmid = e.get('pmid', '').strip()
    url = f"https://doi.org/{doi}" if doi else (f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else e.get('url', ''))
    venue = clean(e.get('journal') or e.get('booktitle') or e.get('howpublished') or e.get('publisher', ''))
    etype = e.get('ENTRYTYPE', '').lower()
    kind = 'article'
    gl = ' '.join(groups)
    if 'Review article' in kw or 'Reviews' in gl:
        kind = 'review'
    if 'Preprints' in gl or re.search(r'rxiv|preprint|ssrn|research square', venue, re.I):
        kind = 'preprint'
    if etype in ('book', 'incollection', 'inbook') or 'Books & chapters' in gl:
        kind = 'book'
    year = (e.get('year') or '').strip()[:4]
    rec = dict(key=e['ID'], title=title, authors=al, short=short_authors(al), year=year,
               venue=venue, doi=doi, pmid=pmid, url=url, kind=kind, groups=groups,
               why=clean(e.get('comment', '')) if inb else '')
    records.append(rec)
    for g in inb:
        inbox[g].append(rec)
    pe = {k: v for k, v in e.items() if k not in ('abstract', 'file', 'comment', 'note', 'keywords', 'groups', 'owner', 'timestamp', 'readstatus', 'ranking', 'priority', 'urldate')}
    pe['keywords'] = ', '.join(sorted(set(g for g in groups if g in curated or inbox_re.match(g))))
    public_entries.append(pe)

def ysort(r):
    return (-(int(r['year']) if r['year'].isdigit() else 0), r['title'].lower())

BADGE = {'review': '⭐ ', 'preprint': '📘 ', 'book': '📗 ', 'article': ''}

def md_table(recs, why=False):
    rows = ["| Year | Paper | Authors | Journal |" + (" Why |" if why else ""),
            "|---|---|---|---|" + ("---|" if why else "")]
    for r in sorted(recs, key=ysort):
        t = r['title'].replace('|', '\\|')
        link = f"[{t}]({r['url']})" if r['url'] else t
        line = f"| {r['year']} | {BADGE[r['kind']]}{link} | {r['short'].replace('|', '/')} | {r['venue'].replace('|', '/')} |"
        if why:
            line += f" {r['why'].replace('|', '/')} |"
        rows.append(line)
    return '\n'.join(rows)

os.makedirs(os.path.join(OUT, 'sections'), exist_ok=True)
os.makedirs(os.path.join(OUT, 'inbox'), exist_ok=True)
today = datetime.date.today().isoformat()
counts = {}
LEGEND = "⭐ review · 📘 preprint · 📗 book or chapter · titles link to the paper (DOI or PubMed)"
for slug, title, top, subs, blurb in SECTIONS:
    recs = [r for r in records if top in r['groups']]
    counts[slug] = len(recs)
    parts = [f"# {title}", "", f"_{blurb}_", "", f"**{len(recs)} papers** · newest first · {LEGEND}", "",
             "[← Back to library](../README.md)", ""]
    if subs:
        used = set()
        for sg, label in subs:
            srecs = [r for r in recs if sg in r['groups']]
            if not srecs:
                continue
            used |= {r['key'] for r in srecs}
            parts += [f"## {label} ({len(srecs)})", "", md_table(srecs), ""]
        rest = [r for r in recs if r['key'] not in used]
        if rest:
            parts += [f"## Other ({len(rest)})", "", md_table(rest), ""]
    else:
        parts += [md_table(recs), ""]
    open(os.path.join(OUT, 'sections', slug + '.md'), 'w').write('\n'.join(parts))

inbox_pages = []
for g in sorted(inbox, reverse=True):
    fn = g.replace(' ', '-').lower() + '.md'
    inbox_pages.append((g, fn, len(inbox[g])))
    open(os.path.join(OUT, 'inbox', fn), 'w').write('\n'.join([
        f"# {g}", "", f"**{len(inbox[g])} new papers** · {LEGEND}", "", "[← Back to library](../README.md)", "",
        md_table(inbox[g], why=True), ""]))
inbox_index = ["# Inbox", "", "New papers added by the weekly and monthly updates, newest first.", "", "[← Back to library](../README.md)", ""]
inbox_index += [f"- [{g}]({fn}) · {n} papers" for g, fn, n in inbox_pages] or ["_No inbox runs yet. The first weekly update is scheduled for Saturday morning._"]
open(os.path.join(OUT, 'inbox', 'README.md'), 'w').write('\n'.join(inbox_index) + '\n')

total = len(records)
readme = [
    "# Research Library",
    "",
    "A curated reading list in population genetics, protein biophysics and immunology, kept in [JabRef](https://www.jabref.org/) and updated automatically every week.",
    "",
    f"**{total} papers** · last updated {today} · **[Open the searchable library →](https://asimdave11.github.io/research-library/)**",
    "",
    "## Sections",
    "",
    "| Section | Papers | What's in it |",
    "|---|---:|---|",
]
for slug, title, top, subs, blurb in SECTIONS:
    readme.append(f"| [{title}](sections/{slug}.md) | {counts[slug]} | {blurb} |")
readme += ["", "## New this week", ""]
if inbox_pages:
    g, fn, n = inbox_pages[0]
    readme.append(f"[{g}](inbox/{fn}): {n} new papers. [All inbox runs](inbox/README.md)")
else:
    readme.append("The first weekly update runs Saturday morning. New papers will appear in [inbox](inbox/README.md).")
readme += ["", "## Files", "",
           "- `index.html`: searchable, filterable view of every paper",
           "- `sections/`: one page per section, newest papers first",
           "- `inbox/`: weekly and monthly digests of new papers",
           "- `library.bib`: BibTeX for every paper listed here (import into JabRef, Zotero or LaTeX)",
           "", f"_{LEGEND}_", ""]
open(os.path.join(OUT, 'README.md'), 'w').write('\n'.join(readme))

# public bib
bdb = BibDatabase()
bdb.entries = public_entries
w = BibTexWriter()
w.indent = '  '
w.order_entries_by = ('ID',)
open(os.path.join(OUT, 'library.bib'), 'w', encoding='utf-8').write(bibtexparser.dumps(bdb, w))

# html
sec_meta = [{'slug': s[0], 'title': s[1], 'group': s[2], 'subs': [x[0] for x in s[3]], 'subLabels': [x[1] for x in s[3]], 'blurb': s[4], 'n': counts[s[0]]} for s in SECTIONS]
data = json.dumps({'records': records, 'sections': sec_meta, 'updated': today,
                   'inbox': [{'group': g, 'n': n} for g, fn, n in inbox_pages]}, ensure_ascii=False)
tpl = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'template.html'), encoding='utf-8').read()
open(os.path.join(OUT, 'index.html'), 'w', encoding='utf-8').write(tpl.replace('/*__DATA__*/null', data.replace('</', '<\\/')))
print('records', total, 'counts', counts, 'inbox', len(inbox_pages))
