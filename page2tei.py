class PObj():
    # A base class for objects represented by coordinates
    def start_x(self):
        return min(x[0] for x in self.points)
    
    def end_x(self):
        return max(x[0] for x in self.points)
    
    def bbox(self):
        return (self.start_x(), min(x[1] for x in self.points),
                self.end_x(), max(x[1] for x in self.points))
    
    def ul(self):
        bb = self.bbox()
        return min(self.points, key=lambda p: (bb[0]-p[0])**2 + (bb[1]-p[1])**2)
    
    def ur(self):
        bb = self.bbox()
        return min(self.points, key=lambda p: (bb[2]-p[0])**2 + (bb[1]-p[1])**2)
    
    def ll(self):
        bb = self.bbox()
        return min(self.points, key=lambda p: (bb[0]-p[0])**2 + (bb[3]-p[1])**2)
    
    def lr(self):
        bb = self.bbox()
        return min(self.points, key=lambda p: (bb[2]-p[0])**2 + (bb[3]-p[1])**2) 


class Line(PObj):
    def __init__(self, name, text, points, comment, rtype, dropcap=None):
        self.name = name
        self.text = text
        self.points = points
        self.comment = comment if comment is not None else ""
        self.dropcap = dropcap
        self.rtype = rtype
        
    def __repr__(self):
        dc = "" if self.dropcap is None else "[" + self.dropcap.text + "]"
        return "[{}], type {}: »{}{}« ({})".format(
            self.name, self.rtype, dc, self.text, self.comment)
    
    def append(self, l):
        if self.text.endswith(("-", "//")):
            print("Warning: Appending to line ending with »-«")
        if self.rtype != l.rtype:
            print("Warnung: Joining lines of different types.")
        self.text += " " + l.text
        if self.comment and l.comment:
            self.comment = self.comment + "\n" + l.comment
        else:
            self.comment = self.comment + l.comment
        s_ur = self.points.index(self.ur())
        l_ll = l.points.index(l.ll())
        self.points = self.points[:s_ur] + l.points[l_ll:] + l.points[:l_ll] + self.points[s_ur:]
        
    def from_page_line(tl, pagename):
        # construct from PageXML TextLine
        name = pagename.lstrip("0") + "_" + tl.attrib.get("id")
        points = tl.find("./{{{}}}Coords".format(tl.nsmap[None])).attrib.get("points")
        coords = [p.split(",") for p in points.split()]
        coords = [(int(int(c[0])), int(int(c[1]))) for c in coords]
        text = tl.find('./{{{0}}}TextEquiv[@index="0"]/{{{0}}}Unicode'.format(
            tl.nsmap[None])).text.strip()
        return Line(name, text, coords, tl.attrib.get("comments"),
                    tl.getparent().attrib.get("type"))


class Figure(PObj):
    def __init__(self, name, points, mlineheight):
        self.name = name
        self.points = points
        self.mlineheight = mlineheight
        
    def __repr__(self):
        return "[{}] – IMAGE of height {} px –".format(self.name, self.height_px())
    
    def height_l(self):
        return int(round(self.height_px() / self.mlineheight))
    
    def height_px(self):
        bb = self.bbox()
        return bb[3] - bb[1]
    
    def from_page_image(ir, pagename, imageno, mlineheight):
        name = pagename.lstrip("0") + "_img" + repr(imageno)
        coords = ir.find("./{{{}}}Coords".format(ir.nsmap[None])).attrib.get("points")
        coords = [p.split(",") for p in coords.split()]
        coords = [(int(int(c[0])), int(int(c[1]))) for c in coords]
        return Figure(name, coords, mlineheight)



def get_columns(lines, page_width, n=2):
    # divide list of lines into n columns
    s = np.array([l.start_x() for l in lines], dtype=np.float)
    e = np.array([l.end_x() for l in lines], dtype=np.float)
    kde_s = gaussian_kde(s)
    kde_e = gaussian_kde(e)
    #fig = plt.figure()
    #ax = fig.add_subplot(111)
    #ax.plot(s, np.zeros(s.shape), 'k+', ms=20)  # rug plot
    #ax.plot(e, np.zeros(e.shape), 'r+', ms=20)  # rug plot
    x_eval = np.linspace(0, page_width, num=page_width)
    #ax.plot(x_eval, kde_s(x_eval), 'k-')
    #ax.plot(x_eval, kde_e(x_eval), 'r-')
    #plt.show()
    spoints = x_eval[argrelextrema(kde_s(x_eval), np.greater, order=1)]
    epoints = x_eval[argrelextrema(kde_e(x_eval), np.greater, order=1)]
    
    if len(spoints) == len(epoints) == n:
        colseps = []
        return [int(mean(z)) for z in zip(epoints[1:], spoints)]
    else:
        # simply separate page geometrically
        text_s = min(s)
        text_e = max(e)
        col_w = (text_e - text_s) / n
        return [int(text_s + (i * col_w)) for i in range(1, n)]


def lines_split(lines, seps):
    seps = [0, *seps]
    columns = [[] for _ in range(len(seps))]
    for l in lines:
        for n, s in list(enumerate(seps))[::-1]:
            if s < mean(p[0] for p in l.points):
                columns[n].append(l)
                break
    return columns


# Eventuell brauchen wir manche Sachen nicht, z.B. Kopfzeilen, Seitenzahlen etc. In den meisten
# Büchern sind die sowieso nicht drin.
exclude_types = ("signature-mark", "page-number", "header")
lines = []
pcol_to_page = {}

# Iterieren wir über ein dict book={"pagenumber": lxml.etree}. Sorted sollte normalerweise die Seiten in die richtige Reihen-
# folge bringen.
for pname in sorted(book):
    root = book[pname]
    ns = {"ns": root.nsmap[None]}
    tls = root.xpath('//ns:TextEquiv[@index="0"]/ns:Unicode/../..', namespaces=ns)
    irs = root.xpath('//ns:ImageRegion', namespaces=ns)
    # Im Page-Tag stehen ein paar nützliche Metadaten
    page_page = root.find(".//{{{}}}Page".format(root.nsmap[None]))
    page_width = int(page_page.attrib.get("imageWidth"))
    page_height = int(page_page.attrib.get("imageHeight"))
    page_filename = page_page.attrib.get("imageFilename")
    plines = []
    for tl in tls:
        l = Line.from_page_line(tl, pname)
        if l.rtype in exclude_types or len(l.points) < 3:
            continue
        # Initialen mit mehr als einem Buchstaben sind vermutlich falsch ausgezeichnet.
        if l.rtype == "drop-capital" and len(l.text) > 1:
            l.rtype = "paragraph"
        plines.append(l)
    # Die mittlere Zeilenhöhe.
    lheight = median(l.ll()[1] - l.ul()[1] for l in plines if l.rtype == "paragraph")
    pimages = []
    for n, ir in enumerate(irs):
        i = Figure.from_page_image(ir, pname, n, lheight)
        if len(i.points) < 3:
            continue
        pimages.append(i)
    # Separator(en), hier für zwei Spalten
    cseps = get_columns(plines, page_width, 2)
    # Aufteilung nach Spalten
    pcols = lines_split(plines, cseps)
    #pcols = [sorted(c, key=lambda l: l.ul()[1]) for c in pcols]
    picols = lines_split(pimages, cseps)
    #picols = [sorted(c, key=lambda l: l.ul()[1]) for c in picols]
    for n, col in enumerate(pcols):
        # Spalten werden mit Buchstaben benannt
        colname = string.ascii_lowercase[n]
        for o in col + picols[n]:
            p, lno = o.name.split("_", 1)
            o.name = "{}{}_{}".format(p, colname, lno)
        # Die Metadaten für jede Spalte brauchen wir später noch für das TEI-Facsimile und die Bilder  
        pcol_to_page["{}{}".format(p, colname)] = {"image": page_filename, "w": page_width,
                                                   "h": page_height}
        # Zeilen, die innerhalb einer Spalte nebeneinander, nicht untereinander liegen, fassen wir
        # zusammen in eine. Dafür haben unsere Lines die append-Funktion.
        dellines = []
        for l in col:
            if l in dellines or l.rtype == "drop-capital":
                continue
            tojoin = [nl for nl in col
                     if abs(mean((l.ul()[1], l.ur()[1])) - mean((nl.ul()[1], nl.ur()[1]))) < .5 * lheight
                      and nl not in dellines and nl.rtype != "drop-capital"]
            if len(tojoin) > 1:
                tojoin.sort(key=lambda x: x.ul()[0])
                for jl in tojoin[1:]:
                    tojoin[0].append(jl)
                    dellines.append(jl)
        # Initialen werden derjenigen Zeile zugeordnet, deren obere linke Ecke ihrer oberen rechten
        # Ecke am nähsten liegt.
        for dc in [dc for dc in col if dc.rtype == "drop-capital"]:
            plines = [l for l in col if l.rtype != "drop-capital"]
            dc_ur = dc.ur()
            plines = sorted(plines, key=lambda p: (dc.ur()[0] - p.ul()[0])**2 +
                                                  (dc.ur()[1] - p.ul()[1])**2 )
            for p in plines[0:5]:
                if p.text[0].isupper():
                    p.dropcap = dc
                    dellines.append(dc)
                    break
                    
        for l in dellines:
            col.remove(l)
            
        # Die Bilder stecken wir auch noch an die Position, wo sie am besten hinpassen.
        for i in (picols[n]):
            col.append(i)
        col = sorted(col, key=lambda l: l.ul()[1])
        
        lines += col
        

text = ""
facs = etree.fromstring("<facsimile></facsimile>")

def formatline(l, lcount, nonbr=False):
    if type(l) == Figure:
        #handle images <figure facs="#p000_a1r-img1"><note type="koi">height(lines):22</note></figure>
        ltext = '\n<figure facs="#p{}-{}"><note type="koi">height(lines):{}</note></figure>'.format(
                    l.name.split("_")[0], l.name.split("_", 1)[1], l.height_l())
    else:
        # Zeilen, die mit einem umgebrochenen Wort beginnen, das keinen Trennstrich beinhaltet, brauchen
        # das Attribut break="no"
        brtext = ' break="no"' if nonbr else ""
        # Linebreak mit Verlinkung in den Facsimile-Block, der die Koordinaten enthälten
        ltext = '\n<lb n="{}" facs="#p{}-{}"{}/>'.format(lcount,
                                                         l.name.split("_")[0],
                                                         l.name.split("_", 1)[1], brtext)
        # Initialen kommen in die Zeile, werden als <span rend="dropCap"> ausgezeichnet
        if l.dropcap != None:
            if l.dropcap.comment:
                ltext += '<note>{}</note>'.format(escape(l.dropcap.comment))
            ltext += '<span rend="dropCap" facs="#p{}-{}">{}</span>'.format(l.dropcap.name.split("_")[0], 
                                                                           l.dropcap.name.split("_", 1)[1],
                                                                            escape(l.dropcap.text))
        # Markierung für Wortumbruch ist jetzt im <lb>, kann also weg
        rawtext = l.text[:-2] if l.text.endswith("//") else l.text
        ltext += escape(rawtext)
    return ltext
    
pb = ""



# Jetzt generieren wir aus den Zeilen etwas TEI-Ähnliches. Sauber müsste man das natürlich in lxml machen.
for n,l in enumerate(lines):
    if (n and lines[n-1].name.split("_")[0] != l.name.split("_")[0]) or (n == 0):
        pcolname = l.name.split("_")[0]
        pb = '\n\n<pb n="{0}" facs="#p{0}"/>'.format(pcolname)
        # Zeilenzählung, hier auf jeder Seite neu.
        lcount = 0
        pdict = {"ulx": "0", "uly": "0", "lrx": repr(pcol_to_page[pcolname]["w"]),
                 "lry": repr(pcol_to_page[pcolname]["h"])}
        # Wenigstens den facsimile-Block schreibe ich mit lxml...
        sf = etree.SubElement(facs, "surface", pdict)
        pdict["{http://www.w3.org/XML/1998/namespace}id"] = "p{}".format(pcolname)
        imgzone = etree.SubElement(sf, "zone", pdict)
        pimg = etree.SubElement(imgzone, "graphic", {"url": pcol_to_page[pcolname]["image"]})
    
    tzone = etree.SubElement(sf, "zone", 
                             {"{http://www.w3.org/XML/1998/namespace}id": "p{}-{}".format(
                                 l.name.split("_")[0], l.name.split("_", 1)[1]),
                "points": " ".join([repr(c[1])+","+repr(c[0]) for c in l.points]) }) #### points invertiert? TEI doc ist unklar.
    
    if type(l) == Line:
        lcount += 1

    # Ran an den Text. 
    nonbr = type(lines[n-1]) == Line and lines[n-1].text.endswith("//")
    thislinetext = formatline(l, lcount, nonbr=nonbr)
    text += pb + thislinetext
    pb = ""
    
    # Kommentare setzen wir einfach mal ans Zeilenende. Die müssen wir sowieso noch einmal durcharbeiten,
    # um z.B. die <sic>-<corr> Elemente zu setzen, normalerweise mit Regex im Editor.
    if type(l) == Line and l.comment.strip():
        text += '<note>{}</note>'.format(escape(l.comment.strip()))
        

text += "\n</div>"
text = '''<?xml version="1.0" encoding="UTF-8"?>
<body>
{}
</body>
'''.format(text)

# Was hier fehlt: Zusammenbau mit Header