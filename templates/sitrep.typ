// Printed morning brief. Data: --input data=/abs/path/render.json (written by sitrep/render.py)
#let d = json(sys.inputs.data)
#let ink = rgb("#1a1f26")
#let mute = rgb("#66717d")
#let hair = rgb("#cfd5db")
#let wash = rgb("#f2f5f8")
#let navy = rgb("#12355b")
#let teal = rgb("#0b7a75")

#set document(title: d.name + " for " + d.day)
#let mono(s, size: 7.5pt, fill: mute, weight: "medium") = text(font: "IBM Plex Mono", size: size, fill: fill, weight: weight, tracking: 0.06em, s)
#set page(paper: "a4", margin: (x: 19mm, top: 23mm, bottom: 20mm),
  header: [
    #grid(columns: (1fr, auto), mono(upper(d.name), fill: navy, weight: "bold"), mono(upper(d.date)))
    #v(-4pt) #line(length: 100%, stroke: 0.5pt + hair)
  ],
  footer: context [
    #line(length: 100%, stroke: 0.5pt + hair) #v(-4pt)
    #grid(columns: (1fr, auto), mono("MORNING BRIEF"),
      mono("PAGE " + str(counter(page).get().first()) + " OF " + str(counter(page).final().first())))
  ])
#set text(font: ("IBM Plex Sans", "Noto Sans"), size: 10.5pt, fill: ink, lang: "en", hyphenate: false)
#set par(leading: 0.68em, spacing: 1em)

#let spans(rs) = rs.map(r => if r.k == "b" { text(weight: "bold", r.v) } else if r.k == "c" { [] } else { r.v }).join()
#let bullet(body, gap: 0.95em) = block(above: gap, below: gap, breakable: false,
  grid(columns: (5mm, 1fr), box(baseline: -2pt, square(size: 3.2pt, fill: teal)), body))
#let secno = counter("sec")
#let part(s) = block(below: 1.3em, width: 100%, sticky: true, stroke: (bottom: 1.2pt + ink), inset: (bottom: 5pt))[
  #secno.step()
  #text(font: "IBM Plex Mono", size: 12pt, weight: "bold", fill: teal)[#context secno.display()]
  #h(6pt) #text(font: "IBM Plex Mono", size: 12pt, weight: "bold", tracking: 0.08em, upper(s))]
#let tag(s, fill: navy) = box(fill: fill, inset: (x: 5pt, y: 3pt), mono(upper(s), size: 7.5pt, fill: white, weight: "bold"))
#let eyebrow(s) = mono(upper(s), size: 8pt, fill: teal, weight: "bold")

// ---- page 1: the bottom line ----
#text(font: "IBM Plex Mono", size: 22pt, weight: "bold", fill: navy)[#d.name for #d.day]
#v(-9pt)
#grid(columns: (1fr, 38mm), line(length: 100%, stroke: 3pt + navy), line(length: 100%, stroke: 3pt + teal))
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
#table(columns: (48mm, 1fr), align: horizon, inset: (x: 0pt, y: 6.5pt),
  stroke: (x, y) => (bottom: 0.5pt + hair, top: if y == 0 { 1pt + navy }),
  ..d.fronts.map(f => (tag(f.label), text(size: 10pt, weight: "medium", f.title))).flatten())
#if d.quiet.len() > 0 { v(3pt); text(size: 9pt, fill: mute)[Nothing significant: #d.quiet.join(", ").] }

#if d.timeline.len() > 0 {
  v(6pt); eyebrow("Timeline (Israel time)"); v(-2pt)
  grid(columns: (16mm, 1fr), row-gutter: 6pt, ..d.timeline.map(e => (text(size: 9.5pt, weight: "bold", e.t), text(size: 9.5pt, spans(e.label)))).flatten())
}

// ---- page 2: assessment ----
#pagebreak()
#part("Assessment")
#for (i, a) in d.analysis.enumerate() {
  let main = a.heading == "Synthesis"
  block(above: 1.3em, below: 0pt, width: 100%, breakable: false, fill: if main { wash },
    stroke: (left: 3pt + if main { teal } else { navy }), inset: (x: 12pt, y: 9pt))[
    #tag(a.heading, fill: if main { teal } else { navy })
    #v(1pt)
    #text(size: 12.5pt, weight: "semibold", fill: navy, a.claim)
    #for b in a.body { if b.k == "li" { bullet(spans(b.r)) } else if b.k == "p" { par(spans(b.r)) } }
  ]
}

// ---- situation ----
#pagebreak(weak: true)
#part("Around the fronts")
#for f in d.fronts {
  block(above: 2em, below: 1em, sticky: true)[
    #tag(f.label)
    #v(-3pt)
    #text(size: 13pt, weight: "semibold", fill: navy, f.title)]
  for b in f.bullets { bullet(spans(b), gap: 0.8em) }
}

#if d.outlook.len() > 0 {
  v(2.2em)
  part("Outlook")
  table(columns: (16mm, 30mm, 1fr), align: horizon, inset: (x, y) => (left: if x == 0 { 0pt } else { 4mm }, right: 0pt, y: 7pt),
    stroke: (x, y) => (bottom: 0.5pt + hair),
    ..d.outlook.map(o => (text(font: "IBM Plex Mono", size: 13pt, weight: "bold", fill: teal)[#o.pct%],
      box(width: 100%, height: 5pt, fill: hair, align(left, rect(width: o.pct * 1%, height: 100%, fill: teal, stroke: none))),
      text(size: 10pt, spans(o.text)))).flatten())
}
#if d.watch.len() > 0 {
  v(1.2em)
  block(width: 100%, breakable: false, fill: wash, stroke: (left: 3pt + navy), inset: (x: 12pt, y: 9pt))[
    #tag("Watch today")
    #for w in d.watch { bullet(spans(w)) }]
}

#if d.sources.len() > 0 {
  pagebreak(weak: true)
  part("Sources")
  set text(size: 8pt, fill: mute)
  for s in d.sources [#s.name: #link(s.url, s.url.replace("/", "/\u{200b}")) \ ]
}
#v(1fr)
#text(size: 8pt, fill: mute)[Compiled automatically from open sources by a language model. It can be wrong.]
