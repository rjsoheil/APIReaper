# -*- coding: utf-8 -*-

from burp import IBurpExtender, ITab

from javax.swing import (
    JPanel, JButton, JTextField, JTextArea,
    JScrollPane, JFileChooser,
    JTabbedPane, JLabel, JSplitPane, JTree,
    BorderFactory, JCheckBox, JComboBox, JDialog,
    JOptionPane, JPopupMenu, JMenuItem, JTable,
    SwingUtilities, BoxLayout
)
from javax.swing.table import DefaultTableModel
from javax.swing.tree import DefaultMutableTreeNode, DefaultTreeModel, DefaultTreeCellRenderer
from javax.swing.event import TreeSelectionListener, DocumentListener, ChangeListener
from java.awt import BorderLayout, Color, FlowLayout, Insets, Font, Toolkit, Desktop, Cursor
from java.awt.datatransfer import StringSelection
from java.net import URI

import json


AUTHOR_NAME = "Soheil Rajaei"
GITHUB_URL = "https://github.com/rjsoheil/"
LINKEDIN_URL = "https://www.linkedin.com/in/soheil-rajaei-1b0805243/"


METHOD_LABEL = {
    "GET":     "[GET]   ",
    "POST":    "[POST]  ",
    "PUT":     "[PUT]   ",
    "DELETE":  "[DEL]   ",
    "PATCH":   "[PATCH] ",
    "HEAD":    "[HEAD]  ",
    "OPTIONS": "[OPT]   ",
}

METHOD_COLOR = {
    "GET":     Color(80, 180, 80),
    "POST":    Color(210, 180, 50),
    "PUT":     Color(80, 130, 210),
    "DELETE":  Color(210, 80, 80),
    "PATCH":   Color(160, 80, 210),
    "HEAD":    Color(130, 130, 130),
    "OPTIONS": Color(130, 130, 130),
}

VALID_METHODS = {"get", "post", "put", "delete", "patch", "head", "options"}


class BurpExtender(IBurpExtender, ITab):

    def registerExtenderCallbacks(self, callbacks):
        self.nodeMap     = {}
        self.callbacks   = callbacks
        self.helpers     = callbacks.getHelpers()

        callbacks.setExtensionName("APIReaper")

        self.requests    = []
        self.edited      = {}
        self.names       = []
        self.groups      = []
        self.colorCache  = {}
        self.loadedData  = None
        self.filterDialog = None
        self.rawData     = None

        self.visibleIndices = []
        self.currentIdx     = None
        self._ignoreChange  = False
        self.openTabs       = {}

        self.root = JTabbedPane()
        self.buildWorkspaceTab()
        self.buildSummaryTab()
        self.buildLogsTab()
        self.buildAboutTab()

        callbacks.addSuiteTab(self)

    def getTabCaption(self):
        return "APIReaper"

    def getUiComponent(self):
        return self.root

    # WORKSPACE TAB

    def buildWorkspaceTab(self):
        panel    = JPanel(BorderLayout())
        top      = JPanel(BorderLayout())
        configBar = JPanel(FlowLayout(FlowLayout.LEFT, 6, 4))
        treeBar  = JPanel(FlowLayout(FlowLayout.LEFT, 6, 2))

        self.baseUrlField   = JTextField("https://example.com:8443/api/v1/", 25)
        self.authField      = JTextField("Authorization: Bearer {{TOKEN}}", 30)
        self.authProfileBox = JComboBox()
        self.authProfileBox.addItem("Custom")
        self.authProfileBox.addItem("No Auth")
        self.authProfileBox.addItem("User Token")
        self.authProfileBox.addItem("Admin Token")
        self.authProfileBox.addActionListener(self.applyAuthProfile)

        self.endpointSearchField = JTextField(18)
        self.endpointSearchField.addActionListener(self.filterTree)
        self.endpointSearchField.getDocument().addDocumentListener(self.LiveFilterWatcher(self))
        self.bodySearchField = JTextField(16)
        self.bodySearchField.addActionListener(self.filterTree)
        self.bodySearchField.getDocument().addDocumentListener(self.LiveFilterWatcher(self))
        self.modifiedOnlyBox = JCheckBox("Modified only")
        self.modifiedOnlyBox.addActionListener(self.filterTree)
        self.methodBoxes = {}
        for method in ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"):
            box = JCheckBox(method)
            box.setSelected(True)
            box.addActionListener(self.filterTree)
            self.methodBoxes[method] = box

        self.totalCountLabel    = JLabel("Total: 0")
        self.modifiedCountLabel = JLabel("Modified: 0")
        self.openTabsLabel      = JLabel("Open tabs: 0")
        self.filterSummaryLabel = JLabel("Filters: All")

        configBar.add(JLabel("Base URL:"))
        configBar.add(self.baseUrlField)
        configBar.add(JLabel("Auth Profile:"))
        configBar.add(self.authProfileBox)
        configBar.add(JLabel("Auth Header:"))
        configBar.add(self.authField)

        self.loadBtn    = JButton("Import",         actionPerformed=self.loadFile)
        self.rebuildBtn = JButton("Apply / Rebuild", actionPerformed=self.rebuildRequests)
        self.loadBtn.setBackground(Color(230, 135, 45))
        self.loadBtn.setForeground(Color.WHITE)
        self.loadBtn.setOpaque(True)

        configBar.add(self.loadBtn)
        configBar.add(self.rebuildBtn)

        self.filtersBtn = JButton("Filters", actionPerformed=self.showFilterDialog)
        treeBar.add(self.filtersBtn)
        treeBar.add(self.filterSummaryLabel)
        treeBar.add(self.totalCountLabel)
        treeBar.add(self.modifiedCountLabel)
        treeBar.add(self.openTabsLabel)

        top.add(configBar, BorderLayout.NORTH)
        top.add(treeBar,   BorderLayout.SOUTH)
        panel.add(top, BorderLayout.NORTH)

        self.rootNode  = DefaultMutableTreeNode("ROOT")
        self.treeModel = DefaultTreeModel(self.rootNode)

        self.tree = JTree(self.treeModel)
        self.tree.setRootVisible(False)
        self.tree.setShowsRootHandles(True)
        self.tree.addTreeSelectionListener(self.TreeHandler(self))
        self.tree.setCellRenderer(self.ColoredRenderer(self))

        editorPanel = JPanel(BorderLayout())

        statusBar = JPanel(FlowLayout(FlowLayout.LEFT, 5, 2))
        self.editLabel     = JLabel("No request selected")
        self.modifiedLabel = JLabel("")
        self.modifiedLabel.setForeground(Color(210, 160, 50))
        statusBar.add(self.editLabel)
        statusBar.add(self.modifiedLabel)
        editorPanel.add(statusBar, BorderLayout.NORTH)

        self.requestTabs = JTabbedPane()
        self.requestTabs.addChangeListener(self.TabHandler(self))
        editorPanel.add(self.requestTabs, BorderLayout.CENTER)

        # ACTION BAR
        actionBar = JPanel(FlowLayout(FlowLayout.LEFT, 6, 4))

        # Repeater Options dropdown
        self.repeaterBtn = JButton("Options V")
        self.repeaterBtn.setBackground(Color(80, 130, 210))
        self.repeaterBtn.setForeground(Color.WHITE)
        self.repeaterBtn.setOpaque(True)
        self.repeaterBtn.addActionListener(self.showRepeaterMenu)

        self._repeaterMenu = JPopupMenu()
        miSingle   = JMenuItem("Send to Repeater")
        miIntruder = JMenuItem("Send to Intruder")
        miAll      = JMenuItem("Send All (Search filter is applied)")
        miModified = JMenuItem("Send Modified")

        miSingle.addActionListener(self.sendToRepeater)
        miIntruder.addActionListener(self.sendToIntruder)
        miAll.addActionListener(self.sendAll)
        miModified.addActionListener(self.sendModified)

        self._repeaterMenu.add(miSingle)
        self._repeaterMenu.add(miIntruder)
        self._repeaterMenu.addSeparator()
        self._repeaterMenu.add(miAll)
        self._repeaterMenu.add(miModified)

        self.resetBtn = JButton("Reset Changes", actionPerformed=self.resetRequest)

        self.setEditorButtons(False)

        actionBar.add(self.repeaterBtn)
        actionBar.add(self.resetBtn)

        editorPanel.add(actionBar, BorderLayout.SOUTH)

        split = JSplitPane(
            JSplitPane.HORIZONTAL_SPLIT,
            JScrollPane(self.tree),
            editorPanel
        )
        split.setDividerLocation(320)
        panel.add(split, BorderLayout.CENTER)

        self.root.addTab("Workspace", panel)

    def showRepeaterMenu(self, event):
        self._repeaterMenu.show(self.repeaterBtn, 0, self.repeaterBtn.getHeight())

    def setEditorButtons(self, enabled):
        self.repeaterBtn.setEnabled(enabled)
        self.resetBtn.setEnabled(enabled)

    def applyAuthProfile(self, event):
        selected = self.safeText(self.authProfileBox.getSelectedItem())
        if selected == "No Auth":
            self.authField.setText("")
        elif selected == "User Token":
            self.authField.setText("Authorization: Bearer {{USER_TOKEN}}")
        elif selected == "Admin Token":
            self.authField.setText("Authorization: Bearer {{ADMIN_TOKEN}}")

    # DOCUMENT SUMMARY TAB

    def buildSummaryTab(self):
        panel = JPanel(BorderLayout())

        toolbar = JPanel(FlowLayout(FlowLayout.LEFT, 6, 4))
        refreshBtn = JButton("Refresh Summary", actionPerformed=self.refreshSummary)
        copyBtn    = JButton("Copy Table",       actionPerformed=self.copySummaryTable)
        toolbar.add(refreshBtn)
        toolbar.add(copyBtn)
        panel.add(toolbar, BorderLayout.NORTH)

        self.summaryTabs = JTabbedPane()

        # --- Endpoints ---
        self.endpointTableModel = DefaultTableModel(
            ["#", "Method", "Group", "Name", "Path"], 0
        )
        self.endpointTable = JTable(self.endpointTableModel)
        self.summaryTabs.addTab("Endpoints", JScrollPane(self.endpointTable))

        # --- Query Params ---
        self.queryTableModel = DefaultTableModel(
            ["Endpoint", "Method", "Param", "Example"], 0
        )
        self.queryTable = JTable(self.queryTableModel)
        self.summaryTabs.addTab("Query Params", JScrollPane(self.queryTable))

        # --- Body Params (Request) ---
        self.bodyReqTableModel = DefaultTableModel(
            ["Endpoint", "Method", "Param", "Type", "Example"], 0
        )
        self.bodyReqTable = JTable(self.bodyReqTableModel)
        self.summaryTabs.addTab("Body Params (Request)", JScrollPane(self.bodyReqTable))

        # --- Body Params (Response) ---
        self.bodyRespTableModel = DefaultTableModel(
            ["Endpoint", "Method", "Status", "Param", "Type", "Example"], 0
        )
        self.bodyRespTable = JTable(self.bodyRespTableModel)
        self.summaryTabs.addTab("Body Params (Response)", JScrollPane(self.bodyRespTable))

        panel.add(self.summaryTabs, BorderLayout.CENTER)
        self.root.addTab("Document Summary", panel)

    def refreshSummary(self, event):
        self.endpointTableModel.setRowCount(0)
        self.queryTableModel.setRowCount(0)
        self.bodyReqTableModel.setRowCount(0)
        self.bodyRespTableModel.setRowCount(0)

        if self.rawData is None:
            self.log("No file loaded for summary.")
            return

        try:
            self.buildSummaryFromData(self.rawData)
            self.log("Summary refreshed.")
        except Exception as e:
            import traceback
            self.log("Summary error: " + str(e))
            self.log(traceback.format_exc())

    def buildSummaryFromData(self, data):
        root = data
        if isinstance(data, dict) and "collection" in data:
            root = data["collection"]

        if isinstance(root, dict) and "item" in root:
            self.summarizePostman(root["item"], "ROOT")
        elif isinstance(data, dict) and "paths" in data:
            self.summarizeOpenApi(data)

    def summarizePostman(self, items, group):
        for i in items:
            name = i.get("name", "Unnamed")
            if "item" in i:
                self.summarizePostman(i["item"], name)
                continue
            req = i.get("request")
            if not req:
                continue
            if isinstance(req, basestring):
                req = {"method": "GET", "url": req}

            method  = req.get("method", "GET").upper()
            url_obj = req.get("url", {})
            path    = self.extractPath(url_obj)

            row_num = self.endpointTableModel.getRowCount() + 1
            self.endpointTableModel.addRow([str(row_num), method, group, name, path])

            endpoint_label = method + " " + path

            # Query params
            if isinstance(url_obj, dict):
                for p in url_obj.get("query", []):
                    key = p.get("key", "")
                    val = p.get("value", "")
                    if key:
                        self.queryTableModel.addRow([endpoint_label, method, key, self.safeText(val)])

            # Body params (request)
            body_obj = req.get("body")
            if isinstance(body_obj, dict):
                mode = body_obj.get("mode", "")
                if mode == "raw":
                    raw_body = body_obj.get("raw", "")
                    try:
                        parsed = json.loads(raw_body)
                        self.flattenJsonToTable(self.bodyReqTableModel, endpoint_label, method, parsed, "")
                    except:
                        pass
                elif mode == "urlencoded":
                    for p in body_obj.get("urlencoded", []):
                        if p.get("key"):
                            self.bodyReqTableModel.addRow([endpoint_label, method, p["key"], "string", self.safeText(p.get("value", ""))])
                elif mode == "formdata":
                    for p in body_obj.get("formdata", []):
                        if p.get("key"):
                            self.bodyReqTableModel.addRow([endpoint_label, method, p["key"], p.get("type","string"), self.safeText(p.get("value", ""))])

            # Body params (response examples)
            for resp in i.get("response", []) or []:
                status = self.safeText(resp.get("status", resp.get("code", "?")))
                resp_body = resp.get("body", "")
                if resp_body:
                    try:
                        parsed = json.loads(resp_body)
                        self.flattenJsonToRespTable(self.bodyRespTableModel, endpoint_label, method, status, parsed, "")
                    except:
                        pass

    def summarizeOpenApi(self, spec):
        paths = spec.get("paths", {})
        for path in paths:
            path_item = paths[path]
            if not isinstance(path_item, dict):
                continue
            common_params = path_item.get("parameters", []) or []
            for method in path_item:
                if method.lower() not in VALID_METHODS:
                    continue
                operation  = path_item[method] or {}
                tags       = operation.get("tags", [])
                group      = self.safeText(tags[0]) if tags else "OPENAPI"
                name       = operation.get("operationId") or operation.get("summary") or (method.upper() + " " + path)
                row_num    = self.endpointTableModel.getRowCount() + 1
                self.endpointTableModel.addRow([str(row_num), method.upper(), group, name, path])

                endpoint_label = method.upper() + " " + path
                all_params = list(common_params) + list(operation.get("parameters", []) or [])

                # Query params
                for p in all_params:
                    if not isinstance(p, dict) or p.get("in") != "query":
                        continue
                    pname = p.get("name", "")
                    ex    = self.safeText(self.exampleValue(p))
                    self.queryTableModel.addRow([endpoint_label, method.upper(), pname, ex])

                # Body params request
                req_body = operation.get("requestBody")
                if isinstance(req_body, dict):
                    content = req_body.get("content", {})
                    for ctype in content:
                        media  = content[ctype]
                        schema = media.get("schema", {}) if isinstance(media, dict) else {}
                        if isinstance(schema, dict):
                            self.schemaToTable(self.bodyReqTableModel, endpoint_label, method.upper(), schema, "")

                # Body params response
                responses = operation.get("responses", {})
                for status_code in responses:
                    resp_obj = responses[status_code]
                    if not isinstance(resp_obj, dict):
                        continue
                    content = resp_obj.get("content", {})
                    for ctype in content:
                        media  = content[ctype]
                        if not isinstance(media, dict):
                            continue
                        # example
                        if "example" in media:
                            ex = media["example"]
                            if isinstance(ex, dict):
                                self.flattenJsonToRespTable(self.bodyRespTableModel, endpoint_label, method.upper(), self.safeText(status_code), ex, "")
                            continue
                        schema = media.get("schema", {})
                        if isinstance(schema, dict):
                            self.schemaToRespTable(self.bodyRespTableModel, endpoint_label, method.upper(), self.safeText(status_code), schema, "")

    def flattenJsonToTable(self, model, endpoint, method, obj, prefix):
        if isinstance(obj, dict):
            for k in obj:
                full_key = (prefix + "." + str(k)) if prefix else str(k)
                val = obj[k]
                if isinstance(val, dict) or isinstance(val, list):
                    self.flattenJsonToTable(model, endpoint, method, val, full_key)
                else:
                    t = type(val).__name__
                    model.addRow([endpoint, method, full_key, t, self.safeText(val)])
        elif isinstance(obj, list) and obj:
            self.flattenJsonToTable(model, endpoint, method, obj[0], prefix + "[]")

    def flattenJsonToRespTable(self, model, endpoint, method, status, obj, prefix):
        if isinstance(obj, dict):
            for k in obj:
                full_key = (prefix + "." + str(k)) if prefix else str(k)
                val = obj[k]
                if isinstance(val, dict) or isinstance(val, list):
                    self.flattenJsonToRespTable(model, endpoint, method, status, val, full_key)
                else:
                    t = type(val).__name__
                    model.addRow([endpoint, method, status, full_key, t, self.safeText(val)])
        elif isinstance(obj, list) and obj:
            self.flattenJsonToRespTable(model, endpoint, method, status, obj[0], prefix + "[]")

    def schemaToTable(self, model, endpoint, method, schema, prefix):
        if not isinstance(schema, dict):
            return
        props = schema.get("properties", {})
        for k in props:
            full_key = (prefix + "." + str(k)) if prefix else str(k)
            prop = props[k]
            if not isinstance(prop, dict):
                continue
            t = prop.get("type", "object")
            ex = self.safeText(self.exampleValue(prop))
            if t == "object":
                self.schemaToTable(model, endpoint, method, prop, full_key)
            elif t == "array":
                self.schemaToTable(model, endpoint, method, prop.get("items", {}), full_key + "[]")
            else:
                model.addRow([endpoint, method, full_key, t, ex])

    def schemaToRespTable(self, model, endpoint, method, status, schema, prefix):
        if not isinstance(schema, dict):
            return
        props = schema.get("properties", {})
        for k in props:
            full_key = (prefix + "." + str(k)) if prefix else str(k)
            prop = props[k]
            if not isinstance(prop, dict):
                continue
            t = prop.get("type", "object")
            ex = self.safeText(self.exampleValue(prop))
            if t == "object":
                self.schemaToRespTable(model, endpoint, method, status, prop, full_key)
            elif t == "array":
                self.schemaToRespTable(model, endpoint, method, status, prop.get("items", {}), full_key + "[]")
            else:
                model.addRow([endpoint, method, status, full_key, t, ex])

    def copySummaryTable(self, event):
        idx = self.summaryTabs.getSelectedIndex()
        tables = [self.endpointTable, self.queryTable, self.bodyReqTable, self.bodyRespTable]
        models = [self.endpointTableModel, self.queryTableModel, self.bodyReqTableModel, self.bodyRespTableModel]
        if idx < 0 or idx >= len(models):
            return
        model = models[idx]
        sb = []
        cols = []
        for c in range(model.getColumnCount()):
            cols.append(self.safeText(model.getColumnName(c)))
        sb.append("\t".join(cols))
        for r in range(model.getRowCount()):
            row = []
            for c in range(model.getColumnCount()):
                val = model.getValueAt(r, c)
                row.append(self.safeText(val) if val is not None else "")
            sb.append("\t".join(row))
        text = "\n".join(sb)
        try:
            Toolkit.getDefaultToolkit().getSystemClipboard().setContents(StringSelection(text), None)
            self.log("Table copied (" + str(model.getRowCount()) + " rows).")
        except Exception as e:
            self.log("Copy failed: " + str(e))

    # LOGS TAB

    def buildLogsTab(self):
        panel = JPanel(BorderLayout())
        self.logArea = JTextArea()
        panel.add(JScrollPane(self.logArea), BorderLayout.CENTER)
        self.root.addTab("Logs", panel)

    # ABOUT TAB

    def buildAboutTab(self):
        panel = JPanel(BorderLayout())
        panel.setBackground(Color(48, 48, 48))
        panel.setBorder(BorderFactory.createEmptyBorder(20, 24, 18, 24))

        header = JLabel(
            ""
        )
        panel.add(header, BorderLayout.NORTH)

        content = JPanel()
        content.setLayout(BoxLayout(content, BoxLayout.Y_AXIS))
        content.setBackground(Color(48, 48, 48))
        content.setBorder(BorderFactory.createEmptyBorder(22, 0, 18, 0))

        content.add(self.aboutSection(
            "Version",
            "1.0"
        ))
        content.add(self.aboutSection(
            "About APIReaper",
            "APIReaper is a Burp Suite extension built to turn Postman, Swagger/OpenAPI, HAR "
            "and simple JSON endpoint documents into editable HTTP requests. It helps API "
            "security testers import large endpoint collections, review requests, edit headers and "
            "bodies, filter endpoints, and send selected traffic to Burp Repeater or Intruder."
        ))
        content.add(self.aboutSection(
            "About the Author",
            "Created by " + AUTHOR_NAME + ", with a focus on practical API penetration testing "
            "workflows, faster endpoint review, and cleaner request preparation inside Burp Suite."
        ))
        content.add(self.aboutSection(
            "Feedback and Contributions",
            "Feedback, feature ideas, and contributions are welcome. The goal is to keep improving "
            "APIReaper into a focused, tester-friendly assistant for working with real-world API specs "
            "and endpoint collections."
        ))

        panel.add(JScrollPane(content), BorderLayout.CENTER)

        links = JPanel(BorderLayout())
        links.setBackground(Color(48, 48, 48))

        githubBtn = JButton("Follow me on GitHub", actionPerformed=lambda event: self.openUrl(GITHUB_URL))
        githubBtn.setBackground(Color(225, 105, 48))
        githubBtn.setForeground(Color.WHITE)
        githubBtn.setOpaque(True)

        linkedinBtn = JButton("Connect with me on LinkedIn", actionPerformed=lambda event: self.openUrl(LINKEDIN_URL))
        linkedinBtn.setBackground(Color(70, 75, 78))
        linkedinBtn.setForeground(Color.WHITE)
        linkedinBtn.setOpaque(True)

        links.add(githubBtn, BorderLayout.NORTH)
        links.add(linkedinBtn, BorderLayout.SOUTH)
        panel.add(links, BorderLayout.SOUTH)

        self.root.addTab("About", panel)

    def aboutSection(self, title, body):
        section = JPanel(BorderLayout())
        section.setBackground(Color(58, 58, 58))
        section.setBorder(BorderFactory.createCompoundBorder(
            BorderFactory.createMatteBorder(0, 0, 1, 0, Color(78, 78, 78)),
            BorderFactory.createEmptyBorder(12, 14, 12, 14)
        ))

        titleLabel = JLabel(title)
        titleLabel.setFont(Font("SansSerif", Font.BOLD, 16))
        titleLabel.setForeground(Color(235, 235, 235))
        section.add(titleLabel, BorderLayout.NORTH)

        bodyText = JTextArea(body)
        bodyText.setEditable(False)
        bodyText.setLineWrap(True)
        bodyText.setWrapStyleWord(True)
        bodyText.setFont(Font("SansSerif", Font.PLAIN, 13))
        bodyText.setForeground(Color(218, 218, 218))
        bodyText.setBackground(Color(58, 58, 58))
        bodyText.setBorder(BorderFactory.createEmptyBorder(8, 0, 0, 0))
        bodyText.setFocusable(False)
        bodyText.setCursor(Cursor.getDefaultCursor())
        section.add(bodyText, BorderLayout.CENTER)

        return section

    def openUrl(self, url):
        try:
            if Desktop.isDesktopSupported():
                Desktop.getDesktop().browse(URI(url))
            else:
                self.log("Open this URL manually: " + url)
        except Exception as e:
            try:
                Toolkit.getDefaultToolkit().getSystemClipboard().setContents(StringSelection(url), None)
                self.log("Could not open browser. URL copied to clipboard: " + url)
            except:
                self.log("Could not open URL: " + str(e) + " | " + url)

    # LOAD

    def loadFile(self, event):
        try:
            chooser = JFileChooser()
            if chooser.showOpenDialog(self.root) != JFileChooser.APPROVE_OPTION:
                return

            f   = chooser.getSelectedFile()
            raw = open(f.getAbsolutePath(), "rb").read()
            if raw.startswith(b'\xef\xbb\xbf'):
                raw = raw[3:]

            text = raw.decode("utf-8", "ignore")
            data = json.loads(text)
            self.loadedData = data
            self.rawData    = data   # For summary

            loaded = self.resetAndLoadData(data, True)
            if not loaded:
                self.log("ERROR: Unsupported JSON format.")
            else:
                self.treeModel.reload()
                self.log("Loaded " + str(len(self.requests)) + " requests.")
                self.refreshSummary(None)

        except Exception as e:
            import traceback
            self.log("EXCEPTION: " + str(e))
            self.log(traceback.format_exc())

    def resetAndLoadData(self, data, apply_servers):
        self.requests       = []
        self.edited         = {}
        self.names          = []
        self.groups         = []
        self.visibleIndices = []
        self.currentIdx     = None
        self.rootNode.removeAllChildren()
        self.nodeMap.clear()
        self.closeAllTabs()

        self.editLabel.setText("No request selected")
        self.modifiedLabel.setText("")
        self.setEditorButtons(False)

        loaded = self.loadJsonData(data, apply_servers)
        self.filterTree(None)
        self.updateCounters()
        return loaded

    def rebuildRequests(self, event):
        if self.loadedData is None:
            self.log("No file loaded.")
            return
        loaded = self.resetAndLoadData(self.loadedData, False)
        if loaded:
            self.log("Rebuilt " + str(len(self.requests)) + " requests.")

    def loadJsonData(self, data, apply_servers):
        root = data
        if isinstance(data, dict) and "collection" in data:
            root = data["collection"]
        if isinstance(root, dict) and "item" in root:
            self.walkPostman(root["item"], "ROOT")
            return True
        if isinstance(data, dict) and "paths" in data:
            if apply_servers:
                self.applyServerFromSpec(data)
            self.walkOpenApi(data)
            return True
        if isinstance(data, dict) and "log" in data and isinstance(data["log"], dict):
            self.walkHar(data["log"].get("entries", []))
            return True
        if isinstance(data, dict) and "resources" in data:
            self.walkInsomnia(data.get("resources", []))
            return True
        if isinstance(data, list):
            self.walkGenericList(data, "JSON")
            return True
        if isinstance(data, dict):
            for key in ("requests", "endpoints", "items"):
                if isinstance(data.get(key), list):
                    self.walkGenericList(data.get(key), key.upper())
                    return True
        return False

    # HELPERS

    def parseBaseUrl(self):
        base      = self.baseUrlField.getText().strip()
        use_https = True
        if "://" in base:
            proto, rest = base.split("://", 1)
            use_https   = proto.lower() == "https"
        else:
            rest = base
        parts     = rest.split("/", 1)
        authority = parts[0]
        base_path = ("/" + parts[1].strip("/")) if len(parts) > 1 and parts[1] else ""
        host = authority
        port = 443 if use_https else 80
        if authority.startswith("[") and "]" in authority:
            end = authority.find("]")
            host = authority[1:end]
            if len(authority) > end + 2 and authority[end + 1] == ":":
                try:
                    port = int(authority[end + 2:])
                except:
                    pass
        elif ":" in authority:
            bits = authority.rsplit(":", 1)
            host = bits[0]
            try:
                port = int(bits[1])
            except:
                host = authority
        if not host:
            host = "example.com"
        default_port = (use_https and port == 443) or ((not use_https) and port == 80)
        host_header = host if default_port else host + ":" + str(port)
        return host, base_path, use_https, port, host_header

    def joinPath(self, base_path, path):
        if not path:
            path = "/"
        if not path.startswith("/"):
            path = "/" + path
        if not base_path:
            return path
        return base_path.rstrip("/") + path

    def safeText(self, value):
        if value is None:
            return ""
        try:
            return unicode(value)
        except:
            try:
                return str(value)
            except:
                return "???"

    def exampleValue(self, obj):
        if not isinstance(obj, dict):
            return ""
        if "example" in obj:
            return obj.get("example")
        examples = obj.get("examples")
        if isinstance(examples, dict) and examples:
            first = examples.values()[0]
            if isinstance(first, dict):
                return first.get("value", "")
            return first
        schema = obj.get("schema")
        if isinstance(schema, dict):
            if "example" in schema:
                return schema.get("example")
            enum = schema.get("enum")
            if isinstance(enum, list) and enum:
                return enum[0]
            t = schema.get("type")
            if t in ("integer", "number"):
                return "1"
            if t == "boolean":
                return "true"
        return ""

    def queryFromParameters(self, parameters):
        q = []
        for p in parameters or []:
            if not isinstance(p, dict) or p.get("in") != "query":
                continue
            name = p.get("name")
            if not name:
                continue
            q.append(str(name) + "=" + str(self.exampleValue(p)))
        return ("?" + "&".join(q)) if q else ""

    def buildQuery(self, url_obj):
        if not isinstance(url_obj, dict):
            return ""
        q = []
        for p in url_obj.get("query", []):
            if p.get("key") and not p.get("disabled", False):
                q.append(str(p["key"]) + "=" + str(p.get("value") or ""))
        return ("?" + "&".join(q)) if q else ""

    def buildBody(self, req):
        body = req.get("body")
        if not body:
            return "", None
        mode = body.get("mode", "")
        if mode == "raw":
            d = body.get("raw", "")
            try:
                json.loads(d)
                return d, "application/json"
            except:
                return d, "text/plain"
        if mode == "urlencoded":
            params = [str(p["key"]) + "=" + str(p.get("value") or "")
                      for p in body.get("urlencoded", []) if p.get("key")]
            return "&".join(params), "application/x-www-form-urlencoded"
        if mode == "formdata":
            params = [str(p["key"]) + "=" + str(p.get("value") or "")
                      for p in body.get("formdata", []) if p.get("key")]
            return "&".join(params), "multipart/form-data"
        return "", None

    def sampleFromSchema(self, schema):
        if not isinstance(schema, dict):
            return ""
        if "example" in schema:
            return schema.get("example")
        if "default" in schema:
            return schema.get("default")
        enum = schema.get("enum")
        if isinstance(enum, list) and enum:
            return enum[0]
        if "properties" in schema:
            obj = {}
            for k, v in schema.get("properties", {}).items():
                obj[k] = self.sampleFromSchema(v)
            return obj
        if schema.get("type") == "array":
            return [self.sampleFromSchema(schema.get("items", {}))]
        if schema.get("type") in ("integer", "number"):
            return 1
        if schema.get("type") == "boolean":
            return True
        return "string"

    def buildOpenApiBody(self, operation):
        request_body = operation.get("requestBody")
        if not isinstance(request_body, dict):
            return "", None
        content = request_body.get("content")
        if not isinstance(content, dict):
            return "", None
        preferred = ["application/json", "application/x-www-form-urlencoded", "multipart/form-data", "text/plain"]
        ctype = None
        media = None
        for item in preferred:
            if item in content:
                ctype  = item
                media  = content[item]
                break
        if media is None and content:
            ctype  = content.keys()[0]
            media  = content[ctype]
        if not isinstance(media, dict):
            return "", ctype
        if "example" in media:
            example = media.get("example")
            if isinstance(example, basestring):
                return example, ctype
            return json.dumps(example), ctype
        examples = media.get("examples")
        if isinstance(examples, dict) and examples:
            first = examples.values()[0]
            if isinstance(first, dict):
                value = first.get("value", "")
                if isinstance(value, basestring):
                    return value, ctype
                return json.dumps(value), ctype
        schema = media.get("schema")
        if isinstance(schema, dict):
            sample = self.sampleFromSchema(schema)
            if ctype == "application/json" or isinstance(sample, (dict, list)):
                return json.dumps(sample), ctype
            return str(sample), ctype
        return "", ctype

    def extractPath(self, url_obj):
        raw = ""
        if isinstance(url_obj, basestring):
            raw = url_obj
        elif isinstance(url_obj, dict):
            raw = url_obj.get("raw", "")
        if raw:
            if raw.startswith("{{"):
                slash_idx = raw.find("/")
                path = raw[slash_idx:] if slash_idx != -1 else "/"
            elif "://" in raw:
                after     = raw.split("://", 1)[1]
                slash_idx = after.find("/")
                path      = after[slash_idx:] if slash_idx != -1 else "/"
            else:
                slash_idx = raw.find("/")
                path      = raw[slash_idx:] if slash_idx != -1 else "/"
            if "?" in path:
                path = path.split("?")[0]
            return path
        if isinstance(url_obj, dict):
            parts = url_obj.get("path", [])
            if isinstance(parts, list):
                segs = []
                for p in parts:
                    if isinstance(p, dict):
                        segs.append(p.get("value", ""))
                    else:
                        segs.append(str(p))
                return "/" + "/".join(segs)
        return "/"

    def httpRequest(self, method, path, body, ctype, extra_headers):
        host, base_path, _, _, host_header = self.parseBaseUrl()
        final_path = self.joinPath(base_path, path)
        http  = method.upper() + " " + final_path + " HTTP/1.1\r\n"
        http += "Host: " + host_header + "\r\n"
        seen_headers = {"host": True}
        auth = self.authField.getText().strip()
        if auth:
            header_name = auth.split(":", 1)[0].strip().lower() if ":" in auth else ""
            if header_name:
                seen_headers[header_name] = True
            http += auth + "\r\n"
        for h in extra_headers or []:
            if h:
                header_name = h.split(":", 1)[0].strip().lower() if ":" in h else ""
                if header_name in ("host", "content-length"):
                    continue
                if header_name:
                    seen_headers[header_name] = True
                http += h + "\r\n"
        if ctype and "content-type" not in seen_headers:
            http += "Content-Type: " + ctype + "\r\n"
        if body:
            http += "Content-Length: " + str(len(body.encode("utf-8"))) + "\r\n"
        http += "\r\n"
        if body:
            http += body
        return http

    # WALKERS

    def walkPostman(self, items, group):
        for i in items:
            name = i.get("name", "Unnamed")
            if "item" in i:
                self.walkPostman(i["item"], name)
                continue
            req = i.get("request")
            if not req:
                continue
            if isinstance(req, basestring):
                req = {"method": "GET", "url": req}
            method  = req.get("method", "GET").upper()
            url_obj = req.get("url")
            path    = self.extractPath(url_obj)
            query   = self.buildQuery(url_obj)
            body, ctype = self.buildBody(req)
            headers = []
            for h in req.get("header", []) or []:
                if h.get("key") and not h.get("disabled", False):
                    headers.append(str(h.get("key")) + ": " + str(h.get("value") or ""))
            self.store(self.httpRequest(method, path + query, body, ctype, headers), name, group)

    def applyServerFromSpec(self, spec):
        try:
            servers = spec.get("servers")
            if isinstance(servers, list) and servers:
                url = servers[0].get("url")
                if url and "://" in url:
                    self.baseUrlField.setText(url)
                    return
            schemes   = spec.get("schemes")
            host      = spec.get("host")
            base_path = spec.get("basePath", "")
            if host:
                scheme = "https"
                if isinstance(schemes, list) and schemes:
                    scheme = schemes[0]
                self.baseUrlField.setText(scheme + "://" + host + base_path)
        except:
            pass

    def walkOpenApi(self, spec):
        paths = spec.get("paths", {})
        for path in paths:
            path_item = paths[path]
            if not isinstance(path_item, dict):
                continue
            common_params = path_item.get("parameters", []) or []
            for method in path_item:
                if method.lower() not in VALID_METHODS:
                    continue
                operation = path_item[method] or {}
                op_params = list(common_params) + list(operation.get("parameters", []) or [])
                query = self.queryFromParameters(op_params)
                body, ctype = self.buildOpenApiBody(operation)
                name  = operation.get("operationId") or operation.get("summary") or (method.upper() + " " + path)
                group = "OPENAPI"
                tags  = operation.get("tags")
                if isinstance(tags, list) and tags:
                    group = self.safeText(tags[0])
                self.store(self.httpRequest(method.upper(), path + query, body, ctype, []), name, group)

    def walkHar(self, entries):
        for e in entries:
            req    = e.get("request", {})
            method = req.get("method", "GET")
            url    = req.get("url", "/")
            path   = self.extractPath(url)
            headers = []
            for h in req.get("headers", []) or []:
                name = h.get("name")
                if name and name.lower() not in ("host", "content-length"):
                    headers.append(str(name) + ": " + str(h.get("value") or ""))
            body  = ""
            ctype = None
            post  = req.get("postData")
            if isinstance(post, dict):
                body  = post.get("text", "") or ""
                ctype = post.get("mimeType")
            self.store(self.httpRequest(method, path, body, ctype, headers), method + " " + path, "HAR")

    def walkInsomnia(self, resources):
        for r in resources:
            if not isinstance(r, dict) or r.get("_type") != "request":
                continue
            method = r.get("method", "GET")
            url    = r.get("url", "/")
            path   = self.extractPath(url)
            headers = []
            for h in r.get("headers", []) or []:
                name = h.get("name")
                if name and not h.get("disabled", False):
                    headers.append(str(name) + ": " + str(h.get("value") or ""))
            body  = ""
            ctype = None
            b     = r.get("body")
            if isinstance(b, dict):
                body  = b.get("text", "") or ""
                ctype = b.get("mimeType")
            self.store(self.httpRequest(method, path, body, ctype, headers), r.get("name", method + " " + path), "INSOMNIA")

    def walkGenericList(self, items, group):
        for item in items:
            if not isinstance(item, dict):
                continue
            method = item.get("method", item.get("verb", "GET"))
            path   = item.get("path", item.get("url", item.get("endpoint", "/")))
            name   = item.get("name", method + " " + path)
            body   = item.get("body", "") or ""
            if not isinstance(body, basestring):
                body = json.dumps(body)
            ctype = item.get("contentType") or item.get("content_type")
            self.store(self.httpRequest(method, self.extractPath(path), body, ctype, []), name, group)

    # STORE

    def store(self, req, name, group):
        idx = len(self.requests)
        self.requests.append(req)
        self.names.append(name)
        self.groups.append(group)
        node = DefaultMutableTreeNode(self.makeDisplay(idx))
        self.nodeMap[node] = idx
        self.findOrCreateGroup(group).add(node)

    def findOrCreateGroup(self, group):
        safe_group = self.safeText(group)
        for i in range(self.rootNode.getChildCount()):
            n = self.rootNode.getChildAt(i)
            if n.toString() == safe_group:
                return n
        n = DefaultMutableTreeNode(safe_group)
        self.rootNode.add(n)
        return n

    def makeDisplay(self, idx):
        req    = self.requests[idx]
        method = req.split(" ")[0].upper()
        label  = METHOD_LABEL.get(method, "[???]   ")
        marker = "* " if idx in self.edited else "  "
        return marker + label + self.safeText(self.names[idx])

    def getEffectiveRequest(self, idx):
        if idx in self.edited:
            return self.edited[idx].encode("utf-8")
        return self.requests[idx].encode("utf-8")

    def toolRequestName(self, idx):
        return "[" + self.safeText(self.groups[idx]) + "] " + self.safeText(self.names[idx])

    # FILTER

    def filterTree(self, event):
        endpoint_keyword = self.endpointSearchField.getText().lower().strip()
        body_keyword     = self.bodySearchField.getText().lower().strip()
        modified_only    = self.modifiedOnlyBox.isSelected()
        selected_methods = self.selectedMethods()

        self.rootNode.removeAllChildren()
        self.nodeMap.clear()
        self.visibleIndices = []

        for i in range(len(self.names)):
            if modified_only and i not in self.edited:
                continue
            name   = self.safeText(self.names[i])
            group  = self.safeText(self.groups[i])
            req    = self.edited.get(i, self.requests[i])
            method = req.split(" ")[0].upper()
            if method not in selected_methods:
                continue
            request_line      = req.splitlines()[0] if req.splitlines() else ""
            endpoint_haystack = (name + " " + group + " " + request_line).lower()
            if endpoint_keyword and endpoint_keyword not in endpoint_haystack:
                continue
            if body_keyword:
                _, body = self.splitRequestText(req)
                if body_keyword not in body.lower():
                    continue
            self.visibleIndices.append(i)
            node = DefaultMutableTreeNode(self.makeDisplay(i))
            self.nodeMap[node] = i
            self.findOrCreateGroup(group).add(node)

        self.treeModel.reload()
        self.updateCounters()

    def selectedMethods(self):
        selected = set()
        for method in self.methodBoxes:
            if self.methodBoxes[method].isSelected():
                selected.add(method)
        return selected

    def refreshTreeNode(self, idx):
        for node in list(self.nodeMap.keys()):
            if self.nodeMap.get(node) == idx:
                node.setUserObject(self.makeDisplay(idx))
                self.treeModel.nodeChanged(node)

    def updateCounters(self):
        try:
            visible = len(self.visibleIndices)
            total   = len(self.requests)
            self.totalCountLabel.setText("Visible: " + str(visible) + " / Total: " + str(total))
            self.modifiedCountLabel.setText("Modified: " + str(len(self.edited)))
            self.openTabsLabel.setText("Open tabs: " + str(len(self.openTabs)))
            self.updateFilterSummary()
        except:
            pass

    def updateFilterSummary(self):
        if not hasattr(self, "filterSummaryLabel"):
            return
        bits     = []
        endpoint = self.endpointSearchField.getText().strip()
        body     = self.bodySearchField.getText().strip()
        selected = self.selectedMethods()
        if len(selected) != len(self.methodBoxes):
            bits.append("Methods: " + ",".join(sorted(selected)))
        if endpoint:
            bits.append("Endpoint: " + endpoint)
        if body:
            bits.append("Body: " + body)
        if self.modifiedOnlyBox.isSelected():
            bits.append("Modified")
        self.filterSummaryLabel.setText("Filters: " + (" | ".join(bits) if bits else "All"))

    def showFilterDialog(self, event):
        if self.filterDialog is None:
            self.filterDialog = JDialog()
            self.filterDialog.setTitle("Endpoint Filters")
            self.filterDialog.setModal(False)
            root    = JPanel(BorderLayout())
            fields  = JPanel(FlowLayout(FlowLayout.LEFT, 6, 4))
            methods = JPanel(FlowLayout(FlowLayout.LEFT, 4, 2))
            actions = JPanel(FlowLayout(FlowLayout.RIGHT, 6, 4))
            fields.add(JLabel("Endpoint:"))
            fields.add(self.endpointSearchField)
            fields.add(JLabel("Body param:"))
            fields.add(self.bodySearchField)
            fields.add(self.modifiedOnlyBox)
            methods.add(JLabel("Methods:"))
            for method in ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"):
                methods.add(self.methodBoxes[method])
            clearBtn = JButton("Clear Filters", actionPerformed=self.clearFilters)
            closeBtn = JButton("Close", actionPerformed=lambda ev: self.filterDialog.setVisible(False))
            actions.add(clearBtn)
            actions.add(closeBtn)
            root.add(fields,  BorderLayout.NORTH)
            root.add(methods, BorderLayout.CENTER)
            root.add(actions, BorderLayout.SOUTH)
            self.filterDialog.add(root)
            self.filterDialog.pack()
            self.filterDialog.setLocationRelativeTo(self.root)
        self.filterDialog.setVisible(True)

    def clearFilters(self, event):
        self.endpointSearchField.setText("")
        self.bodySearchField.setText("")
        self.modifiedOnlyBox.setSelected(False)
        for method in self.methodBoxes:
            self.methodBoxes[method].setSelected(True)
        self.filterTree(None)

    class LiveFilterWatcher(DocumentListener):
        def __init__(self, outer):
            self.outer = outer

        def _filter(self):
            self.outer.filterTree(None)

        def insertUpdate(self, e):  self._filter()
        def removeUpdate(self, e):  self._filter()
        def changedUpdate(self, e): self._filter()

    # REQUEST EDITOR

    def makeRequestEditor(self):
        editor = JTextArea()
        editor.setFont(Font("Monospaced", Font.PLAIN, 14))
        editor.setBorder(BorderFactory.createEmptyBorder(4, 6, 4, 6))
        return editor

    def splitRequestText(self, text):
        if "\r\n\r\n" in text:
            parts = text.split("\r\n\r\n", 1)
            return parts[0], parts[1]
        if "\n\n" in text:
            parts = text.split("\n\n", 1)
            return parts[0], parts[1]
        return text, ""

    def composeRequestText(self, headers, body):
        nh = headers.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")
        nb = body.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")
        return nh.rstrip("\r\n") + "\r\n\r\n" + nb

    def syncPartsFromRaw(self, idx, raw_text):
        if idx not in self.openTabs:
            return
        headers, body = self.splitRequestText(raw_text)
        self._ignoreChange = True
        self.openTabs[idx]["headersViewer"].setText(headers)
        self.openTabs[idx]["bodyViewer"].setText(body)
        self.openTabs[idx]["headersViewer"].setCaretPosition(0)
        self.openTabs[idx]["bodyViewer"].setCaretPosition(0)
        self._ignoreChange = False

    def syncRawFromParts(self, idx):
        if idx not in self.openTabs:
            return
        headers   = self.openTabs[idx]["headersViewer"].getText()
        body      = self.openTabs[idx]["bodyViewer"].getText()
        raw_text  = self.composeRequestText(headers, body)
        rawViewer = self.openTabs[idx]["rawViewer"]
        self._ignoreChange = True
        rawViewer.setText(raw_text)
        rawViewer.setCaretPosition(0)
        self._ignoreChange = False
        self.saveRequestText(idx, raw_text)

    def saveRequestText(self, idx, current_text):
        original     = self.requests[idx]
        was_modified = idx in self.edited
        if current_text == original:
            if idx in self.edited:
                del self.edited[idx]
        else:
            self.edited[idx] = current_text
        if was_modified != (idx in self.edited):
            if self.modifiedOnlyBox.isSelected():
                self.filterTree(None)
            else:
                self.refreshTreeNode(idx)
            self.updateTabTitle(idx)
        if self.currentIdx == idx:
            self.updateStatus()
        self.updateCounters()

    def bodyToolPanel(self, idx, bodyViewer):
        panel   = JPanel(BorderLayout())
        toolbar = JPanel(FlowLayout(FlowLayout.LEFT, 5, 3))
        prettyBtn = JButton("Pretty JSON", actionPerformed=lambda ev, i=idx: self.prettyBodyJson(i))
        minifyBtn = JButton("Minify",      actionPerformed=lambda ev, i=idx: self.minifyBodyJson(i))
        copyBtn   = JButton("Copy Body",   actionPerformed=lambda ev, i=idx: self.copyBody(i))
        toolbar.add(prettyBtn)
        toolbar.add(minifyBtn)
        toolbar.add(copyBtn)
        panel.add(toolbar, BorderLayout.NORTH)
        panel.add(JScrollPane(bodyViewer), BorderLayout.CENTER)
        return panel

    def prettyBodyJson(self, idx):
        self.formatBodyJson(idx, True)

    def minifyBodyJson(self, idx):
        self.formatBodyJson(idx, False)

    def formatBodyJson(self, idx, pretty):
        if idx not in self.openTabs:
            return
        bodyViewer = self.openTabs[idx]["bodyViewer"]
        body = bodyViewer.getText().strip()
        if not body:
            return
        try:
            parsed    = json.loads(body)
            formatted = json.dumps(parsed, indent=2, sort_keys=True) if pretty else json.dumps(parsed, separators=(",", ":"))
            self._ignoreChange = True
            bodyViewer.setText(formatted)
            bodyViewer.setCaretPosition(0)
            self._ignoreChange = False
            self.syncRawFromParts(idx)
        except Exception as e:
            self.log("JSON format failed: " + str(e))

    def copyBody(self, idx):
        if idx not in self.openTabs:
            return
        body = self.openTabs[idx]["bodyViewer"].getText()
        try:
            Toolkit.getDefaultToolkit().getSystemClipboard().setContents(StringSelection(body), None)
            self.log("Body copied.")
        except Exception as e:
            self.log("Copy failed: " + str(e))

    # TABS

    def openRequestTab(self, idx):
        if idx in self.openTabs:
            self.requestTabs.setSelectedComponent(self.openTabs[idx]["panel"])
            return
        panel         = JPanel(BorderLayout())
        innerTabs     = JTabbedPane()
        rawViewer     = self.makeRequestEditor()
        headersViewer = self.makeRequestEditor()
        bodyViewer    = self.makeRequestEditor()

        raw_text             = self.edited.get(idx, self.requests[idx])
        headers_text, body_text = self.splitRequestText(raw_text)

        rawViewer.setText(raw_text)
        headersViewer.setText(headers_text)
        bodyViewer.setText(body_text)
        rawViewer.setCaretPosition(0)
        headersViewer.setCaretPosition(0)
        bodyViewer.setCaretPosition(0)

        rawViewer.getDocument().addDocumentListener(self.RawEditWatcher(self, idx, rawViewer))
        headersViewer.getDocument().addDocumentListener(self.PartEditWatcher(self, idx))
        bodyViewer.getDocument().addDocumentListener(self.PartEditWatcher(self, idx))

        innerTabs.addTab("Raw",     JScrollPane(rawViewer))
        innerTabs.addTab("Headers", JScrollPane(headersViewer))
        innerTabs.addTab("Body",    self.bodyToolPanel(idx, bodyViewer))
        panel.add(innerTabs, BorderLayout.CENTER)

        titleLabel  = JLabel(self.tabTitle(idx))
        closeButton = JButton("x")
        closeButton.setFocusable(False)
        closeButton.setMargin(Insets(0, 4, 0, 4))
        closeButton.setBorder(BorderFactory.createEmptyBorder(0, 4, 0, 4))
        closeButton.setContentAreaFilled(False)
        closeButton.addActionListener(lambda ev, i=idx: self.closeTab(i))

        tabHeader = JPanel(FlowLayout(FlowLayout.LEFT, 4, 0))
        tabHeader.setOpaque(False)
        tabHeader.add(titleLabel)
        tabHeader.add(closeButton)

        self.openTabs[idx] = {
            "panel": panel, "innerTabs": innerTabs,
            "rawViewer": rawViewer, "headersViewer": headersViewer,
            "bodyViewer": bodyViewer, "titleLabel": titleLabel, "tabHeader": tabHeader
        }
        self.requestTabs.addTab(self.tabTitle(idx), panel)
        pos = self.requestTabs.indexOfComponent(panel)
        if pos >= 0:
            self.requestTabs.setTabComponentAt(pos, tabHeader)
        self.requestTabs.setSelectedComponent(panel)
        self.updateCounters()

    def tabTitle(self, idx):
        marker = "* " if idx in self.edited else ""
        return marker + self.safeText(self.names[idx])

    def updateTabTitle(self, idx):
        if idx not in self.openTabs:
            return
        panel = self.openTabs[idx]["panel"]
        pos   = self.requestTabs.indexOfComponent(panel)
        if pos >= 0:
            self.requestTabs.setTitleAt(pos, self.tabTitle(idx))
        titleLabel = self.openTabs[idx].get("titleLabel")
        if titleLabel:
            titleLabel.setText(self.tabTitle(idx))

    def getCurrentViewer(self):
        if self.currentIdx is None or self.currentIdx not in self.openTabs:
            return None
        return self.openTabs[self.currentIdx]["rawViewer"]

    def closeTab(self, idx):
        if idx is None or idx not in self.openTabs:
            return
        panel = self.openTabs[idx]["panel"]
        self.requestTabs.remove(panel)
        del self.openTabs[idx]
        self.tree.clearSelection()
        self.updateCurrentFromSelectedTab()
        self.updateCounters()

    def closeAllTabs(self):
        self.openTabs = {}
        self.requestTabs.removeAll()
        self.currentIdx = None
        self.updateCounters()

    def updateCurrentFromSelectedTab(self):
        panel = self.requestTabs.getSelectedComponent()
        self.currentIdx = None
        for idx in self.openTabs:
            if self.openTabs[idx]["panel"] == panel:
                self.currentIdx = idx
                break
        self.updateStatus()

    def updateStatus(self):
        if self.currentIdx is None:
            self.editLabel.setText("No request selected")
            self.modifiedLabel.setText("")
            self.setEditorButtons(False)
            return
        self.editLabel.setText("Editing: " + self.safeText(self.names[self.currentIdx]))
        self.modifiedLabel.setText("[modified]" if self.currentIdx in self.edited else "")
        self.setEditorButtons(True)

    class TabHandler(ChangeListener):
        def __init__(self, outer):
            self.outer = outer

        def stateChanged(self, event):
            self.outer.updateCurrentFromSelectedTab()

    # EDIT WATCHERS

    class RawEditWatcher(DocumentListener):
        def __init__(self, outer, idx, rawViewer):
            self.outer     = outer
            self.idx       = idx
            self.rawViewer = rawViewer

        def _save(self):
            if self.outer._ignoreChange:
                return
            current_text = self.rawViewer.getText()
            self.outer.saveRequestText(self.idx, current_text)
            self.outer.syncPartsFromRaw(self.idx, current_text)

        def insertUpdate(self, e):  self._save()
        def removeUpdate(self, e):  self._save()
        def changedUpdate(self, e): self._save()

    class PartEditWatcher(DocumentListener):
        def __init__(self, outer, idx):
            self.outer = outer
            self.idx   = idx

        def _save(self):
            if self.outer._ignoreChange:
                return
            self.outer.syncRawFromParts(self.idx)

        def insertUpdate(self, e):  self._save()
        def removeUpdate(self, e):  self._save()
        def changedUpdate(self, e): self._save()

    # EDITOR ACTIONS

    def resetRequest(self, event):
        if self.currentIdx is None:
            return
        idx = self.currentIdx
        if idx in self.edited:
            del self.edited[idx]
        viewer = self.getCurrentViewer()
        if viewer:
            self._ignoreChange = True
            viewer.setText(self.requests[idx])
            self._ignoreChange = False
            viewer.setCaretPosition(0)
            self.syncPartsFromRaw(idx, self.requests[idx])
        if self.modifiedOnlyBox.isSelected():
            self.filterTree(None)
        else:
            self.refreshTreeNode(idx)
        self.updateTabTitle(idx)
        self.updateStatus()
        self.updateCounters()

    # TREE HANDLER

    class TreeHandler(TreeSelectionListener):
        def __init__(self, outer):
            self.outer = outer

        def valueChanged(self, event):
            node = self.outer.tree.getLastSelectedPathComponent()
            if not node:
                return
            idx = self.outer.nodeMap.get(node)
            if idx is None or idx >= len(self.outer.requests):
                return
            self.outer.openRequestTab(idx)
            self.outer.currentIdx = idx
            self.outer.updateStatus()

    # COLOR RENDERER

    def getColorForKey(self, key):
        if not key:
            return Color.DARK_GRAY
        k = key.lower()
        if k in self.colorCache:
            return self.colorCache[k]
        h = abs(hash(k))
        c = Color(80 + (h % 120), 80 + ((h >> 8) % 120), 80 + ((h >> 16) % 120))
        self.colorCache[k] = c
        return c

    class ColoredRenderer(DefaultTreeCellRenderer):
        def __init__(self, outer):
            self.outer = outer

        def getTreeCellRendererComponent(self, tree, value, sel, expanded, leaf, row, hasFocus):
            label = DefaultTreeCellRenderer.getTreeCellRendererComponent(
                self, tree, value, sel, expanded, leaf, row, hasFocus
            )
            try:
                idx  = self.outer.nodeMap.get(value)
                text = value.toString().strip()
                if leaf:
                    if idx in self.outer.edited:
                        label.setForeground(Color(255, 170, 30))
                    else:
                        matched = Color.WHITE
                        for method, color in METHOD_COLOR.items():
                            if text.startswith("[" + method + "]") or text.startswith("[" + method[:3]):
                                matched = color
                                break
                        label.setForeground(matched)
                else:
                    label.setForeground(self.outer.getColorForKey(text))
            except:
                pass
            return label

    # SEND

    def sendToRepeater(self, event):
        if self.currentIdx is None:
            return
        host, _, use_https, port, _ = self.parseBaseUrl()
        self.callbacks.sendToRepeater(
            host, port, use_https,
            self.getEffectiveRequest(self.currentIdx),
            self.toolRequestName(self.currentIdx)
        )
        self.modifiedLabel.setText("[sent]")

    def sendToIntruder(self, event):
        if self.currentIdx is None:
            return
        host, _, use_https, port, _ = self.parseBaseUrl()
        self.callbacks.sendToIntruder(
            host, port, use_https,
            self.getEffectiveRequest(self.currentIdx)
        )
        self.modifiedLabel.setText("[sent]")

    def _doSendBatch(self, indices, label):
        if not indices:
            self.log("Nothing to send.")
            return
        host, _, use_https, port, _ = self.parseBaseUrl()
        sent = modified = 0
        for i in indices:
            self.callbacks.sendToRepeater(
                host, port, use_https,
                self.getEffectiveRequest(i),
                self.toolRequestName(i)
            )
            sent += 1
            if i in self.edited:
                modified += 1
        self.log(label + ": " + str(sent) + " sent, " + str(modified) + " modified.")

    def sendAll(self, event):
        target = list(self.visibleIndices)
        if not target:
            self.log("No visible requests to send.")
            return
        confirm = JOptionPane.showConfirmDialog(
            self.root,
            "Send ALL " + str(len(target)) + " visible requests to Repeater?",
            "Send ALL (filtered)", JOptionPane.YES_NO_OPTION
        )
        if confirm == JOptionPane.YES_OPTION:
            self._doSendBatch(target, "Send ALL")

    def sendModified(self, event):
        target = [i for i in self.visibleIndices if i in self.edited]
        if not target:
            self.log("No modified requests in current view.")
            return
        confirm = JOptionPane.showConfirmDialog(
            self.root,
            "Send " + str(len(target)) + " modified (visible) requests to Repeater?",
            "Send Modified (filtered)", JOptionPane.YES_NO_OPTION
        )
        if confirm == JOptionPane.YES_OPTION:
            self._doSendBatch(target, "Send Modified")

    # LOG

    def log(self, msg):
        self.logArea.append(str(msg) + "\n")
        self.callbacks.printOutput(str(msg))
