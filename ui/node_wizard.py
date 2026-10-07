from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit,
    QSpinBox, QTableWidget, QTableWidgetItem, QComboBox, QLabel, QPushButton,
    QDialogButtonBox, QGraphicsScene, QGraphicsView, QHeaderView, QAbstractItemView)
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPen, QColor, QFont, QPainter
from core.component_definition import ComponentDefinition
from core.port import PortDefinition, new_id
from ui.geometry import port_positions


class NodeWizard(QDialog):
    """Create reusable definitions; side/order is the V1 symbol layout."""
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setWindowTitle('New Component — Port / Node Wizard')
        self.resize(860,760)
        self.definition = None
        self.definition_id = new_id()
        self.updating = False
        root = QVBoxLayout(self)
        form = QFormLayout()
        self.name=QLineEdit(); self.name.setPlaceholderText('EHSV or Relief Valve')
        self.prefix=QLineEdit(); self.prefix.setPlaceholderText('EHSV or RV')
        self.category=QLineEdit('Valves')
        self.count=QSpinBox(); self.count.setRange(1,32); self.count.setValue(2)
        form.addRow('Component Name',self.name); form.addRow('Component Prefix',self.prefix)
        form.addRow('Category',self.category); form.addRow('Number of Hydraulic Ports',self.count)
        root.addLayout(form)
        root.addWidget(QLabel('Arrange ports by side; row order controls spacing along each side.'))
        self.ports=QTableWidget(0,5)
        self.ports.setHorizontalHeaderLabels(['Port ID','Display Name','Port Type','Flow Direction','Symbol Side'])
        self.ports.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        root.addWidget(self.ports)
        self.scene=QGraphicsScene(self)
        self.preview=QGraphicsView(self.scene); self.preview.setMinimumHeight(180)
        self.preview.setRenderHint(QPainter.Antialiasing)
        self.preview.setBackgroundBrush(QColor('#f4f7fa'))
        root.addWidget(self.preview)
        root.addWidget(QLabel('Optional internal relationships (never manifold routing channels)'))
        self.relationships=QTableWidget(0,3)
        self.relationships.setHorizontalHeaderLabels(['From Port ID','To Port ID','Relationship Type'])
        self.relationships.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.relationships.setMaximumHeight(115)
        self.relationships.setSelectionBehavior(QAbstractItemView.SelectRows)
        root.addWidget(self.relationships)
        row=QHBoxLayout()
        add=QPushButton('+ Internal Relationship'); remove=QPushButton('Remove Relationship')
        add.clicked.connect(self.add_relationship); remove.clicked.connect(self.remove_relationship)
        row.addWidget(add); row.addWidget(remove); row.addStretch(); root.addLayout(row)
        self.error_label=QLabel(); self.error_label.setStyleSheet('color: #b3261e'); self.error_label.setWordWrap(True)
        root.addWidget(self.error_label)
        buttons=QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.submit); buttons.rejected.connect(self.reject); root.addWidget(buttons)
        self.count.valueChanged.connect(self.set_port_count)
        self.ports.itemChanged.connect(self.update_preview)
        self.name.textChanged.connect(self.update_preview)
        self.set_port_count(2)

    def set_port_count(self,count):
        self.updating=True
        old=self.ports.rowCount()
        self.ports.setRowCount(count)
        for row in range(old,count):
            for column,text in enumerate((f'p{row+1}',f'P{row+1}','HYDRAULIC')):
                self.ports.setItem(row,column,QTableWidgetItem(text))
            flow=QComboBox(); flow.addItems(['UNSPECIFIED','IN','OUT','BIDIRECTIONAL'])
            side=QComboBox(); side.addItems(['LEFT','RIGHT','TOP','BOTTOM'])
            side.setCurrentIndex(row%2)
            self.ports.setCellWidget(row,3,flow); self.ports.setCellWidget(row,4,side)
            flow.currentTextChanged.connect(self.update_preview)
            side.currentTextChanged.connect(self.update_preview)
        self.updating=False
        self.update_preview()

    def text_at(self,table,row,column):
        item=table.item(row,column)
        return item.text().strip() if item else ''

    def build_definition(self):
        ports = [PortDefinition(self.text_at(self.ports,r,0),self.text_at(self.ports,r,1),
                                self.text_at(self.ports,r,2),self.ports.cellWidget(r,3).currentText(),
                                self.ports.cellWidget(r,4).currentText()) for r in range(self.ports.rowCount())]
        relationships=[{'from_port_id':self.text_at(self.relationships,r,0),
                        'to_port_id':self.text_at(self.relationships,r,1),
                        'relationship':self.text_at(self.relationships,r,2) or 'UNSPECIFIED'}
                       for r in range(self.relationships.rowCount())]
        # Grow the generic symbol for components with many ports.
        vertical=max(sum(p.side==s for p in ports) for s in ['LEFT','RIGHT'])
        horizontal=max(sum(p.side==s for p in ports) for s in ['TOP','BOTTOM'])
        return ComponentDefinition(self.definition_id,self.name.text().strip(),self.prefix.text().strip(),
                                   self.category.text().strip(),ports,
                                   symbol={'kind':'box','width':min(1000,max(140,horizontal*45)),'height':max(90,vertical*30)},
                                   internal_relationships=relationships)

    def update_preview(self,*args):
        if self.updating: return
        self.scene.clear()
        d=self.build_definition()
        w=d.symbol['width']; h=d.symbol['height']
        pen=QPen(QColor('#42576a'),1.5)
        self.scene.addRect(-w/2,-h/2,w,h,pen,QColor('white'))
        title=self.scene.addText(d.name or 'Component',QFont('Sans Serif',10))
        title.setPos(-title.boundingRect().width()/2,-14)
        for p in d.ports:
            pos=port_positions(d)[p.id]
            self.scene.addEllipse(pos.x()-4,pos.y()-4,8,8,QPen(QColor('#17657a')),QColor('white'))
            text=self.scene.addText(p.display_name or p.id,QFont('Sans Serif',9))
            tw=text.boundingRect().width(); th=text.boundingRect().height()
            if p.side=='LEFT': text.setPos(pos.x()-tw-8,pos.y()-th/2)
            elif p.side=='RIGHT': text.setPos(pos.x()+8,pos.y()-th/2)
            elif p.side=='TOP': text.setPos(pos.x()-tw/2,pos.y()-th-7)
            else: text.setPos(pos.x()-tw/2,pos.y()+7)
        self.preview.setSceneRect(self.scene.itemsBoundingRect().adjusted(-25,-20,25,20))
        self.preview.fitInView(self.preview.sceneRect(),Qt.KeepAspectRatio)

    def add_relationship(self):
        row=self.relationships.rowCount(); self.relationships.insertRow(row)
        for column in range(3): self.relationships.setItem(row,column,QTableWidgetItem(''))

    def remove_relationship(self):
        rows={i.row() for i in self.relationships.selectedIndexes()}
        for row in sorted(rows,reverse=True): self.relationships.removeRow(row)

    def submit(self):
        try: self.definition=self.build_definition().validate()
        except ValueError as error:
            self.error_label.setText(str(error)); return
        self.accept()
