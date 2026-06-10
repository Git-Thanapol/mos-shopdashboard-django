/* Shared AG Grid builder for all report tables.
 *
 * Reads a JSON config from a <script type="application/json"> element and
 * renders a grid with the LEGACY Streamlit table palette (ui_components.py):
 *   body #1c1c1c / zebra #262626, headers #1e3c72, header groups
 *   slate #2c3e50 / green #27ae60 / orange #e67e22 / blue #3366ff /
 *   purple #691e72 / teal #176f98, negatives #FF0000,
 *   footer rows รวม #010538, sales #2c3e50, cost #3366ff, ads #e67e22,
 *   ops #691e72, com #176f98.
 *
 * Config shape:
 * {
 *   "columns": [{"field","header","sub","type","hdr","pinned","width","link","posGreen","color"}],
 *   "rows": [...],
 *   "footer": [{"rtype": "total|sales|cost|ads|ops|com|grand", ...}]
 * }
 * type: money | money2 | pct | int | text
 * Footer cell values are preformatted strings; day/body cells are numbers.
 */
(function () {
    "use strict";

    var NUM0 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
    var NUM2 = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    var NUM1 = new Intl.NumberFormat("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

    function fmtValue(type, v) {
        if (v === null || v === undefined || v === "") return "-";
        if (typeof v === "string") return v;          // preformatted footer cell
        if (v === 0) return "-";                       // legacy fmt(): zero → "-"
        if (type === "money") return NUM0.format(v);
        if (type === "money2") return NUM2.format(v);
        if (type === "pct") return NUM1.format(v) + "%";
        if (type === "int") return NUM0.format(v);
        return String(v);
    }

    function isNegative(v) {
        if (typeof v === "number") return v < 0;
        if (typeof v === "string") return v.trim().charAt(0) === "-";
        return false;
    }

    /* two-line header: SKU on top, product name underneath (legacy th-sku) */
    function TwoLineHeader() {}
    TwoLineHeader.prototype.init = function (p) {
        this.eGui = document.createElement("div");
        this.eGui.className = "agx-two-line";
        var top = document.createElement("div");
        top.className = "agx-h-main";
        top.textContent = p.displayName;
        this.eGui.appendChild(top);
        if (p.sub) {
            var sub = document.createElement("div");
            sub.className = "agx-h-sub";
            sub.textContent = p.sub;
            this.eGui.appendChild(sub);
        }
    };
    TwoLineHeader.prototype.getGui = function () { return this.eGui; };

    function linkRenderer(p) {
        if (p.value === null || p.value === undefined || p.value === "") return "-";
        if (p.node.rowPinned) return p.value;
        var a = document.createElement("a");
        a.href = "/products/" + encodeURIComponent(p.value) + "/";
        a.textContent = p.value;
        a.className = "agx-link";
        return a;
    }

    function buildColDef(c) {
        var def = {
            field: c.field,
            headerName: c.header,
            headerTooltip: c.sub || c.header,
            headerClass: "agx-hdr-" + (c.hdr || "blue"),
            sortable: c.type !== "text" || !!c.sortText,
            resizable: true,
            // columns auto-fit their content (autoSizeStrategy fitCellContents);
            // floor/cap keep degenerate content from collapsing or exploding them
            minWidth: 70,
            maxWidth: c.type === "text" ? 420 : 190,
            suppressMovable: true,
            valueFormatter: function (p) { return fmtValue(c.type, p.value); },
            cellClass: function (p) {
                var cls = ["agx-cell"];
                if (c.type !== "text") cls.push("agx-num");
                var pinnedTotal = p.node.rowPinned && p.data &&
                    (p.data.rtype === "total" || p.data.rtype === "grand");
                if (isNegative(p.value)) cls.push("agx-neg");
                else if (pinnedTotal && c.posGreen) cls.push("agx-foot-profit");
                else if (pinnedTotal && c.color === "ads") cls.push("agx-foot-ads");
                else if (!p.node.rowPinned) {
                    if (c.posGreen && typeof p.value === "number" && p.value > 0) cls.push("agx-pos");
                    else if (c.color && (!c.posOnly || (typeof p.value === "number" && p.value > 0))) {
                        cls.push("agx-c-" + c.color);
                    }
                }
                return cls;
            },
            tooltipValueGetter: c.sub ? function () { return c.sub; } : undefined,
        };
        if (c.pinned) def.pinned = "left";
        if (c.sub) {
            def.headerComponent = TwoLineHeader;
            def.headerComponentParams = { sub: c.sub };
        }
        if (c.link) def.cellRenderer = linkRenderer;
        if (c.type === "text") def.cellClass = "agx-cell agx-text";
        return def;
    }

    var FOOTER_BG = {
        total: "#010538",
        sales: "#2c3e50",
        cost: "#3366ff",
        ads: "#e67e22",
        ops: "#691e72",
        com: "#176f98",
        grand: "#1e3c72",
    };

    window.initReportGrid = function (mountId, dataId, opts) {
        opts = opts || {};
        var el = document.getElementById(mountId);
        var cfg = JSON.parse(document.getElementById(dataId).textContent);
        var colDefs = cfg.columns.map(buildColDef);

        var gridOptions = {
            columnDefs: colDefs,
            rowData: cfg.rows,
            pinnedBottomRowData: cfg.footer || [],
            headerHeight: opts.twoLine ? 40 : 32,
            rowHeight: 28,
            animateRows: false,
            suppressCellFocus: true,
            enableCellTextSelection: true,
            tooltipShowDelay: 300,
            autoSizeStrategy: { type: "fitCellContents" },
            defaultColDef: { suppressHeaderMenuButton: true },
            getRowStyle: function (p) {
                if (p.node.rowPinned && p.data && p.data.rtype) {
                    return {
                        backgroundColor: FOOTER_BG[p.data.rtype] || "#1e3c72",
                        fontWeight: "700",
                        color: "#ffffff",
                    };
                }
                return null;
            },
        };

        var api = agGrid.createGrid(el, gridOptions);

        var exportBtn = document.getElementById(mountId + "-export");
        if (exportBtn) {
            exportBtn.addEventListener("click", function () {
                api.exportDataAsCsv({ fileName: (opts.exportName || "report") + ".csv" });
            });
        }
        return api;
    };
})();
