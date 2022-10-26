from nanome.api import structure


def cpk_colors(a):
    colors = {}
    colors["xx"] = "#030303"
    colors["h"] = "#FFFFFF"
    colors["he"] = "#D9FFFF"
    colors["li"] = "#CC80FF"
    colors["be"] = "#C2FF00"
    colors["b"] = "#FFB5B5"
    colors["c"] = "#909090"
    colors["n"] = "#3050F8"
    colors["o"] = "#FF0D0D"
    colors["f"] = "#B5FFFF"
    colors["ne"] = "#B3E3F5"
    colors["na"] = "#AB5CF2"
    colors["mg"] = "#8AFF00"
    colors["al"] = "#BFA6A6"
    colors["si"] = "#F0C8A0"
    colors["p"] = "#FF8000"
    colors["s"] = "#FFFF30"
    colors["cl"] = "#1FF01F"
    colors["ar"] = "#80D1E3"
    colors["k"] = "#8F40D4"
    colors["ca"] = "#3DFF00"
    colors["sc"] = "#E6E6E6"
    colors["ti"] = "#BFC2C7"
    colors["v"] = "#A6A6AB"
    colors["cr"] = "#8A99C7"
    colors["mn"] = "#9C7AC7"
    colors["fe"] = "#E06633"
    colors["co"] = "#F090A0"
    colors["ni"] = "#50D050"
    colors["cu"] = "#C88033"
    colors["zn"] = "#7D80B0"
    colors["ga"] = "#C28F8F"
    colors["ge"] = "#668F8F"
    colors["as"] = "#BD80E3"
    colors["se"] = "#FFA100"
    colors["br"] = "#A62929"
    colors["kr"] = "#5CB8D1"
    colors["rb"] = "#702EB0"
    colors["sr"] = "#00FF00"
    colors["y"] = "#94FFFF"
    colors["zr"] = "#94E0E0"
    colors["nb"] = "#73C2C9"
    colors["mo"] = "#54B5B5"
    colors["tc"] = "#3B9E9E"
    colors["ru"] = "#248F8F"
    colors["rh"] = "#0A7D8C"
    colors["pd"] = "#006985"
    colors["ag"] = "#C0C0C0"
    colors["cd"] = "#FFD98F"
    colors["in"] = "#A67573"
    colors["sn"] = "#668080"
    colors["sb"] = "#9E63B5"
    colors["te"] = "#D47A00"
    colors["i"] = "#940094"
    colors["xe"] = "#429EB0"
    colors["cs"] = "#57178F"
    colors["ba"] = "#00C900"
    colors["la"] = "#70D4FF"
    colors["ce"] = "#FFFFC7"
    colors["pr"] = "#D9FFC7"
    colors["nd"] = "#C7FFC7"
    colors["pm"] = "#A3FFC7"
    colors["sm"] = "#8FFFC7"
    colors["eu"] = "#61FFC7"
    colors["gd"] = "#45FFC7"
    colors["tb"] = "#30FFC7"
    colors["dy"] = "#1FFFC7"
    colors["ho"] = "#00FF9C"
    colors["er"] = "#00E675"
    colors["tm"] = "#00D452"
    colors["yb"] = "#00BF38"
    colors["lu"] = "#00AB24"
    colors["hf"] = "#4DC2FF"
    colors["ta"] = "#4DA6FF"
    colors["w"] = "#2194D6"
    colors["re"] = "#267DAB"
    colors["os"] = "#266696"
    colors["ir"] = "#175487"
    colors["pt"] = "#D0D0E0"
    colors["au"] = "#FFD123"
    colors["hg"] = "#B8B8D0"
    colors["tl"] = "#A6544D"
    colors["pb"] = "#575961"
    colors["bi"] = "#9E4FB5"
    colors["po"] = "#AB5C00"
    colors["at"] = "#754F45"
    colors["rn"] = "#428296"
    colors["fr"] = "#420066"
    colors["ra"] = "#007D00"
    colors["ac"] = "#70ABFA"
    colors["th"] = "#00BAFF"
    colors["pa"] = "#00A1FF"
    colors["u"] = "#008FFF"
    colors["np"] = "#0080FF"
    colors["pu"] = "#006BFF"
    colors["am"] = "#545CF2"
    colors["cm"] = "#785CE3"
    colors["bk"] = "#8A4FE3"
    colors["cf"] = "#A136D4"
    colors["es"] = "#B31FD4"
    colors["fm"] = "#B31FBA"
    colors["md"] = "#B30DA6"
    colors["no"] = "#BD0D87"
    colors["lr"] = "#C70066"
    colors["rf"] = "#CC0059"
    colors["db"] = "#D1004F"
    colors["sg"] = "#D90045"
    colors["bh"] = "#E00038"
    colors["hs"] = "#E6002E"
    colors["mt"] = "#EB0026"
    colors["ds"] = "#ED0023"
    colors["rg"] = "#F00021"
    colors["cn"] = "#E5001E"
    colors["nh"] = "#F4001C"
    colors["fl"] = "#F70019"
    colors["mc"] = "#FA0019"
    colors["lv"] = "#FC0017"
    colors["ts"] = "#FC0014"
    colors["og"] = "#FC000F"
    a_type = a.symbol.lower()
    if a_type not in colors:
        return [1.0, 0, 1.0, 1.0]  # Pink unknown
    h = colors[a_type].lstrip('#')
    return list(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)) + [1.0]


def create_hidden_complex(comp_name=None):
    # Create a nanome complex to attach the mesh to
    # create viewport sphere and position at current map position
    comp = structure.Complex()
    molecule = structure.Molecule()
    chain = structure.Chain()
    residue = structure.Residue()

    if comp_name:
        comp.name = comp_name
    comp.add_molecule(molecule)
    molecule.add_chain(chain)
    chain.add_residue(residue)

    # create invisible atoms to create bounding box
    for i in [-10, 10]:
        atom = structure.Atom()
        atom.set_visible(False)
        atom.position.set(i, i, i)
        residue.add_atom(atom)
    return comp
