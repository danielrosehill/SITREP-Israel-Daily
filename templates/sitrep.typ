// Printed SITREP. Data: --input data=/abs/path/render.json (written by sitrep/render.py)
#let d = json(sys.inputs.data)
#let ink = rgb("#12181f")
#let mute = rgb("#5d6873")
#let hair = rgb("#c4cbd2")
#let wash = rgb("#f1f4f6")
#let navy = rgb("#12355b")
#let alert = rgb("#b3261e")
#let amber = rgb("#b86e00")
#let score = d.at("score", default: none)
#let level = if score == none { navy } else if score >= 4 { alert } else if score == 3 { amber } else { navy }

#let mono(s, size: 7pt, fill: mute, weight: "medium") = text(font: "IBM Plex Mono", size: size, fill: fill, weight: weight, tracking: 0.06em, s)
#let marking = mono("UNCLASSIFIED // OPEN SOURCE // AI-GENERATED", size: 6.5pt, weight: "semibold")

#set document(title: d.title, author: d.name)
#set page(paper: "a4", margin: (x: 17mm, top: 21mm, bottom: 19mm),
  header: [
    #grid(columns: (1fr, auto, 1fr), align: (left, center, right),
      mono(d.ref), marking, mono(d.dtg))
    #v(-4pt) #line(length: 100%, stroke: 0.5pt + hair)
  ],
  footer: context [
    #line(length: 100%, stroke: 0.5pt + hair) #v(-4pt)
    #grid(columns: (1fr, auto, 1fr), align: (left, center, right),
      mono(d.name), marking,
      mono("PAGE " + str(counter(page).get().first()) + " / " + str(counter(page).final().first())))
  ])
#set text(font: ("IBM Plex Sans", "Noto Sans"), size: 9.4pt, fill: ink, lang: "en", hyphenate: false)
#set par(leading: 0.58em, spacing: 0.8em, justify: false)

#let spans(rs) = rs.map(r => if r.k == "b" { strong(r.v) } else if r.k == "c" {
  text(size: 0.8em, fill: mute)[\[#r.v\]] } else { r.v }).join()

#let bullet(n, body) = block(above: 0.55em, below: 0.75em, inset: (left: n * 4mm),
  grid(columns: (3.4mm, 1fr),
    if n == 0 { box(baseline: -1.6pt, square(size: 2.6pt, fill: navy)) } else { box(baseline: -2.2pt, line(length: 4pt, stroke: 0.7pt + mute)) },
    body))

#let render(bs) = for b in bs {
  if b.k == "h" { block(above: 1em, below: 0.5em, sticky: true, text(weight: "semibold", size: 9.2pt, fill: navy, b.v)) }
  else if b.k == "li" { bullet(b.n, spans(b.r)) }
  else { par(spans(b.r)) }
}

#let part(s) = block(above: 1.6em, below: 0.8em, sticky: true, width: 100%,
  stroke: (bottom: 1pt + ink), inset: (bottom: 3pt),
  text(font: "IBM Plex Mono", weight: "semibold", size: 9pt, tracking: 0.1em, upper(s)))

#let cell(label, body, fill: ink) = [
  #mono(upper(label), size: 6pt) \
  #v(-3pt) #text(size: 9.5pt, weight: "semibold", fill: fill, body)]

// ---- masthead ----
#grid(columns: (1fr, auto), align: (left + bottom, right + bottom),
  text(font: "IBM Plex Mono", weight: "bold", size: 22pt, tracking: 0.04em, d.name),
  text(size: 9.5pt, fill: mute, d.date))
#v(-3pt)
#line(length: 100%, stroke: 2.2pt + level)
#v(1pt)
#block(stroke: (bottom: 0.5pt + hair), inset: (bottom: 6pt), width: 100%,
  grid(columns: (1fr, 1.7fr, 1fr, 1.2fr), column-gutter: 5mm,
    cell("Issued (local / UTC)", d.local + " / " + d.utc + "Z"),
    cell("Coverage", d.from + " – " + d.to),
    cell("Precedence", d.urgency, fill: level),
    [#mono("SEVERITY " + if score == none { "N/A" } else { str(score) + " / 5" }, size: 6pt) \
     #v(-3pt) #grid(columns: (1fr,) * 5, column-gutter: 1.5pt,
       ..range(1, 6).map(i => rect(width: 100%, height: 6pt, stroke: 0.5pt + hair,
         fill: if score != none and i <= score { level } else { none })))]))

#v(2pt)
#block(above: 1em, below: 1em, text(size: 16pt, weight: "semibold", d.title))

#block(width: 100%, fill: wash, stroke: (left: 3pt + level), inset: (x: 10pt, y: 8pt), breakable: false)[
  #mono("BLUF — BOTTOM LINE UP FRONT", size: 6.5pt, fill: level, weight: "bold")
  #v(1pt)
  #set text(size: 10.4pt, weight: "medium")
  #render(d.bluf)
]

#v(3pt)
#grid(columns: (1fr,) * 3, column-gutter: 5mm,
  ..d.highlights.enumerate().map(((i, h)) => block(width: 100%, stroke: (top: 1pt + navy), inset: (top: 5pt))[
    #mono("KEY " + str(i + 1), size: 6.5pt, fill: navy, weight: "bold") \
    #text(size: 8.8pt, spans(h))]))

#v(4pt)
#render(d.topline)

#if d.posture != none {
  block(width: 100%, stroke: 0.5pt + hair, inset: 6pt, breakable: false,
    grid(columns: (auto, 1fr), column-gutter: 8pt, align: horizon,
      mono("HOME FRONT: " + d.posture.tier, size: 7pt, weight: "bold",
        fill: if d.posture.tier == "FULL" { alert } else if d.posture.tier == "LIMITED" { amber } else { navy }),
      text(size: 8.6pt, d.posture.note)))
}

// ---- situation ----
#part("1. Situation by front")
#for s in d.sections {
  block(above: 1.25em, below: 0.6em, sticky: true)[
    #box(fill: navy, inset: (x: 4pt, y: 2.5pt), mono(upper(s.label), size: 6.8pt, fill: white, weight: "bold"))
    #if s.title != "" and s.title != s.label { h(5pt); text(weight: "semibold", size: 10.6pt, s.title) }
  ]
  render(s.body)
}
#if d.quiet.len() > 0 {
  block(above: 1.2em, width: 100%, stroke: (top: 0.5pt + hair), inset: (top: 5pt),
    [#mono("NOSIG", weight: "bold") #h(4pt) #text(size: 8.2pt, fill: mute, d.quiet.join(" · "))])
}

#if d.timeline.len() > 0 {
  part("2. Timeline (local time)")
  table(columns: (auto, auto, 1fr), stroke: (x, y) => (bottom: 0.4pt + hair), inset: (x: 4pt, y: 4pt),
    ..d.timeline.map(e => (mono(e.t, size: 7pt, fill: ink), text(size: 8pt, fill: mute, e.front), text(size: 8.6pt, spans(e.label)))).flatten())
}

#part("3. Assessment")
#for a in d.analysis {
  block(above: 1em, below: 0.5em, sticky: true, mono(upper(a.heading), size: 7.4pt, fill: navy, weight: "bold"))
  render(a.body)
}

#part("4. Outlook")
#let preds(label, ps, color) = block(width: 100%, stroke: (top: 1.2pt + color), inset: (top: 5pt))[
  #mono(upper(label), size: 7pt, fill: color, weight: "bold")
  #for p in ps {
    grid(columns: (11mm, 1fr), column-gutter: 2mm,
      if p.conf != none { text(font: "IBM Plex Mono", weight: "bold", size: 9pt, fill: color)[#p.conf%] },
      text(size: 8.8pt, spans(p.text)))
    v(1pt)
  }]
#grid(columns: (1fr, 1fr), column-gutter: 7mm,
  preds("Baseline", d.stable, navy), preds("Escalatory tail", d.escalatory, alert))

#if d.assumptions.len() > 0 {
  block(above: 1.2em, below: 0.4em, sticky: true, mono("KEY ASSUMPTIONS", size: 7.4pt, fill: navy, weight: "bold"))
  for a in d.assumptions { bullet(0, [#spans(a.text) #text(size: 8.4pt, fill: mute)[_Fails if:_ #spans(a.falsifier)]]) }
}

#part("5. Watch list")
#for i in d.indicators { bullet(0, spans(i)) }

#if d.sources.len() > 0 {
  part("Sources")
  set text(size: 7pt, fill: mute)
  show link: set text(size: 6.4pt)
  let col(gs) = for g in gs {
    block(above: 0.6em, below: 0.3em, sticky: true, text(fill: ink, weight: "semibold", g.name))
    for u in g.urls { block(above: 0.35em, below: 0.35em, link(u, u.replace("https://", "").replace("www.", "").replace("/", "/\u{200b}").replace("-", "-\u{200b}"))) }
  }
  grid(columns: (1fr, 1fr), column-gutter: 6mm, col(d.sources.at(0)), col(d.sources.at(1)))
}

#v(1em)
#text(size: 7pt, fill: mute)[Compiled automatically from open sources by a language model (#d.model). It can be wrong. Check primary sources before acting, and follow Home Front Command instructions for safety decisions.]
