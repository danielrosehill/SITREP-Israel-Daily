// Printed morning brief. Data: --input data=/abs/path/render.json (written by sitrep/render.py)
#let d = json(sys.inputs.data)
#let ink = rgb("#1a1f26")
#let mute = rgb("#66717d")
#let hair = rgb("#cfd5db")
#let wash = rgb("#f2f5f8")
#let navy = rgb("#12355b")
#let teal = rgb("#0b7a75")

#set document(title: d.name + " for " + d.day)
#set page(paper: "a4", margin: (x: 22mm, top: 20mm, bottom: 20mm),
  footer: context [
    #set text(size: 8pt, fill: mute)
    #line(length: 100%, stroke: 0.5pt + hair) #v(-3pt)
    #grid(columns: (1fr, auto), d.date, [Page #counter(page).get().first() of #counter(page).final().first()])
  ])
#set text(font: ("IBM Plex Sans", "Noto Sans"), size: 11pt, fill: ink, lang: "en", hyphenate: false)
#set par(leading: 0.68em, spacing: 1em)

#let spans(rs) = rs.map(r => if r.k == "b" { text(weight: "bold", r.v) } else if r.k == "c" { [] } else { r.v }).join()
#let bullet(body, gap: 0.95em) = block(above: gap, below: gap, breakable: false,
  grid(columns: (5mm, 1fr), box(baseline: -2pt, square(size: 3.2pt, fill: teal)), body))
#let part(s) = block(below: 1.2em, width: 100%, sticky: true, stroke: (bottom: 1.4pt + navy), inset: (bottom: 5pt),
  text(size: 17pt, weight: "bold", fill: navy, s))
#let eyebrow(s) = text(size: 9pt, weight: "bold", fill: teal, tracking: 0.07em, upper(s))

// ---- page 1: the bottom line ----
#text(size: 25pt, weight: "bold", fill: navy)[#d.name for #d.day]
#v(-8pt)
#line(length: 100%, stroke: 2pt + navy)
#v(4pt)
#text(size: 16pt, weight: "semibold", d.headline)
#v(4pt)
#block(width: 100%, fill: wash, stroke: (left: 4pt + navy), inset: (x: 14pt, y: 13pt), breakable: false)[
  #eyebrow("Bottom line up front")
  #set text(size: 12pt)
  #for b in d.bluf { bullet(spans(b)) }
]
#v(4pt)
#spans(d.picture)

#if d.posture != none [
  #block(width: 100%, stroke: 0.7pt + teal, inset: 9pt)[*Home front:* #d.posture]
]

#v(6pt)
#eyebrow("In this brief")
#v(-2pt)
#grid(columns: (46mm, 1fr), row-gutter: 8pt,
  ..d.fronts.map(f => (text(size: 10pt, weight: "bold", fill: teal, f.label), text(size: 10pt, f.title))).flatten())
#if d.quiet.len() > 0 { v(3pt); text(size: 9pt, fill: mute)[Nothing significant: #d.quiet.join(", ").] }

#if d.timeline.len() > 0 {
  v(6pt); eyebrow("Timeline (Israel time)"); v(-2pt)
  grid(columns: (16mm, 1fr), row-gutter: 6pt, ..d.timeline.map(e => (text(size: 9.5pt, weight: "bold", e.t), text(size: 9.5pt, spans(e.label)))).flatten())
}

// ---- page 2: assessment ----
#pagebreak()
#part("Assessment")
#for a in d.analysis {
  block(above: 1.7em, below: 0.8em, sticky: true)[#eyebrow(a.heading) \ #v(-2pt) #text(size: 13pt, weight: "semibold", fill: navy, a.claim)]
  for b in a.body { if b.k == "li" { bullet(spans(b.r)) } else if b.k == "p" { par(spans(b.r)) } }
}

// ---- situation ----
#pagebreak(weak: true)
#part("Around the fronts")
#for f in d.fronts {
  block(above: 2em, below: 1em, sticky: true)[
    #eyebrow(f.label) \
    #v(-2pt)
    #text(size: 13.5pt, weight: "semibold", fill: navy, f.title)]
  for b in f.bullets { bullet(spans(b), gap: 0.8em) }
}

#if d.outlook.len() > 0 {
  v(2.2em)
  part("Outlook")
  for o in d.outlook {
    block(above: 1em, below: 1em, breakable: false, grid(columns: (18mm, 1fr), align: (left, left + horizon),
      text(size: 15pt, weight: "bold", fill: teal)[#o.pct%], spans(o.text)))
  }
}
#if d.watch.len() > 0 {
  v(1.2em)
  block(below: 0.6em, sticky: true, text(size: 13pt, weight: "bold", fill: navy)[Watch today])
  for w in d.watch { bullet(spans(w)) }
}

#if d.sources.len() > 0 {
  pagebreak(weak: true)
  part("Sources")
  set text(size: 8pt, fill: mute)
  for s in d.sources [#s.name: #link(s.url, s.url.replace("/", "/\u{200b}")) \ ]
}
#v(1fr)
#text(size: 8pt, fill: mute)[Compiled automatically from open sources by a language model. It can be wrong.]
