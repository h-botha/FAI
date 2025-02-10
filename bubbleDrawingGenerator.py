# -*- coding: utf-8 -*-
"""
Created on Sun Feb  9 13:08:32 2025

@author: hendrik
"""

import sys
import os
import fitz  # PyMuPDF
from PyQt5.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, 
                             QLabel, QPushButton, QFileDialog, QWidget, QScrollArea,
                             QMessageBox)
from PyQt5.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QFont
from PyQt5.QtCore import Qt, QPoint
import PyPDF2
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
import io


class PDFViewer(QScrollArea):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.document = None
        self.total_pages = 0
        self.current_page = None
        self.page_width = 0
        self.page_height = 0
        self.display_width = 0
        self.display_height = 0
        self.zoom = 2  # Display zoom factor
        self.scale_factor = 1  # Will store the scaling between display and PDF

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.setWidget(self.image_label)
        self.setWidgetResizable(True)
        self.image_label.setMouseTracking(True)
        self.image_label.mousePressEvent = self.on_click

    def load_pdf(self, pdf_path):
        self.document = fitz.open(pdf_path)
        self.total_pages = len(self.document)
        self.show_page(0)

    def show_page(self, page_number):
        if not self.document:
            return

        page = self.document[page_number]
        
        # Store original PDF dimensions
        self.page_width = page.rect.width
        self.page_height = page.rect.height

        # Create display image
        mat = fitz.Matrix(self.zoom, self.zoom)
        pix = page.get_pixmap(matrix=mat)
        
        # Store display dimensions
        self.display_width = pix.width
        self.display_height = pix.height
        
        # Calculate scale factor between display and PDF
        self.scale_factor = self.display_width / self.page_width
        
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(img)
        
        self.display_pixmap_with_bubbles(pixmap)

    def on_click(self, event):
        display_x = event.pos().x()
        display_y = event.pos().y()
        
        # Convert to PDF coordinates
        pdf_x = display_x / self.scale_factor
        pdf_y = display_y / self.scale_factor
        
        self.parent.add_bubble_position(pdf_x, pdf_y)
        self.display_current_page_bubbles()

    def display_pixmap_with_bubbles(self, pixmap):
        display_pixmap = pixmap.copy()
        painter = QPainter(display_pixmap)
        
        pen = QPen(QColor(255, 0, 0))
        pen.setWidth(1)
        painter.setPen(pen)
        
        font = QFont()
        font.setPointSize(8)
        painter.setFont(font)
        
        # Get bubbles for current page and total bubble count before this page
        current_page_bubbles = self.parent.get_bubbles_for_page(self.parent.current_page_number)
        previous_bubbles_count = self.parent.get_bubble_count_before_page(self.parent.current_page_number)
        
        for idx, (x, y) in enumerate(current_page_bubbles, previous_bubbles_count + 1):
            # Convert PDF coordinates to display coordinates
            display_x = x * self.scale_factor
            display_y = y * self.scale_factor
            
            # Draw bubble
            painter.drawEllipse(QPoint(int(display_x), int(display_y)), 5, 5)
            painter.drawText(QPoint(int(display_x-3), int(display_y+3)), str(idx))
        
        painter.end()
        self.image_label.setPixmap(display_pixmap)

    def display_current_page_bubbles(self):
        if self.image_label.pixmap():
            self.display_pixmap_with_bubbles(self.image_label.pixmap())

class InteractivePDFBubblePlacer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.current_pdf_path = None
        self.bubbles_by_page = {}  # Dictionary to store bubbles for each page
        self.current_page_number = 0

    def initUI(self):
        # [Previous UI setup code remains the same]
        self.setWindowTitle('First Article Inspection Bubble Placer')
        self.setGeometry(100, 100, 1200, 800)

        main_widget = QWidget()
        main_layout = QHBoxLayout()
        
        self.pdf_viewer = PDFViewer(self)
        main_layout.addWidget(self.pdf_viewer)

        control_panel = QWidget()
        control_layout = QVBoxLayout()

        load_pdf_btn = QPushButton('Load PDF')
        load_pdf_btn.clicked.connect(self.load_pdf)
        control_layout.addWidget(load_pdf_btn)

        nav_layout = QHBoxLayout()
        prev_page_btn = QPushButton('Previous Page')
        next_page_btn = QPushButton('Next Page')
        prev_page_btn.clicked.connect(self.prev_page)
        next_page_btn.clicked.connect(self.next_page)
        nav_layout.addWidget(prev_page_btn)
        nav_layout.addWidget(next_page_btn)
        control_layout.addLayout(nav_layout)

        self.page_label = QLabel('Page: 0/0')
        control_layout.addWidget(self.page_label)

        self.bubble_list = QLabel('Bubble Positions:')
        control_layout.addWidget(self.bubble_list)

        clear_bubbles_btn = QPushButton('Clear All Bubbles')
        clear_bubbles_btn.clicked.connect(self.clear_bubbles)
        control_layout.addWidget(clear_bubbles_btn)

        clear_page_bubbles_btn = QPushButton('Clear Page Bubbles')
        clear_page_bubbles_btn.clicked.connect(self.clear_page_bubbles)
        control_layout.addWidget(clear_page_bubbles_btn)

        generate_btn = QPushButton('Generate Bubble Overlay')
        generate_btn.clicked.connect(self.generate_bubble_overlay)
        control_layout.addWidget(generate_btn)

        control_panel.setLayout(control_layout)
        main_layout.addWidget(control_panel)

        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

    def get_bubbles_for_page(self, page_number):
        return self.bubbles_by_page.get(page_number, [])

    def get_bubble_count_before_page(self, page_number):
        count = 0
        for page in range(page_number):
            count += len(self.bubbles_by_page.get(page, []))
        return count

    def add_bubble_position(self, x, y):
        if self.current_page_number not in self.bubbles_by_page:
            self.bubbles_by_page[self.current_page_number] = []
        self.bubbles_by_page[self.current_page_number].append((x, y))
        self.update_bubble_list()

    def update_bubble_list(self):
        bubble_text = 'Bubble Positions:\n'
        total_count = 0
        
        # Check if there are any bubbles
        if not self.bubbles_by_page:
            self.bubble_list.setText(bubble_text)
            return
            
        max_page = max(self.bubbles_by_page.keys())
        
        for page in range(max_page + 1):
            page_bubbles = self.bubbles_by_page.get(page, [])
            if page_bubbles:
                bubble_text += f'\nPage {page + 1}:\n'
                for i, (x, y) in enumerate(page_bubbles, total_count + 1):
                    bubble_text += f'{i}: ({x:.2f}, {y:.2f})\n'
                total_count += len(page_bubbles)
                
        self.bubble_list.setText(bubble_text)

    def clear_bubbles(self):
        self.bubbles_by_page.clear()
        self.update_bubble_list()
        self.pdf_viewer.display_current_page_bubbles()

    def clear_page_bubbles(self):
        if self.current_page_number in self.bubbles_by_page:
            del self.bubbles_by_page[self.current_page_number]
        self.update_bubble_list()
        self.pdf_viewer.display_current_page_bubbles()

    def create_bubble_overlay(self, input_pdf, output_pdf):
        """Create PDF with bubble overlays for all pages"""
        try:
            with open(input_pdf, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                pdf_writer = PyPDF2.PdfWriter()
                
                # Process all pages
                for page_number in range(len(pdf_reader.pages)):
                    # Get the original page
                    original_page = pdf_reader.pages[page_number]
                    
                    # If no bubbles on this page, just add the original page
                    if page_number not in self.bubbles_by_page or not self.bubbles_by_page[page_number]:
                        pdf_writer.add_page(original_page)
                        continue
                    
                    # Create overlay PDF with same dimensions as input page
                    packet = io.BytesIO()
                    can = canvas.Canvas(packet, pagesize=(original_page.mediabox.width, original_page.mediabox.height))
                    
                    # Get bubbles for this page
                    bubbles = self.bubbles_by_page.get(page_number, [])
                    previous_bubbles = self.get_bubble_count_before_page(page_number)
                    
                    # Draw bubbles using PDF coordinates
                    for idx, (x, y) in enumerate(bubbles, previous_bubbles + 1):
                        # Flip Y coordinate for PDF
                        pdf_y = float(original_page.mediabox.height) - float(y)
                        
                        can.setStrokeColorRGB(1, 0, 0)  # Pure red
                        can.circle(float(x), pdf_y, 10, stroke=1, fill=0)
                        
                        can.setFillColorRGB(1, 0, 0)
                        can.setFont('Helvetica', 8)
                        can.drawCentredString(float(x), pdf_y - 3, str(idx))
                    
                    can.save()
                    packet.seek(0)
                    overlay_pdf = PyPDF2.PdfReader(packet)
                    
                    # Create merged page
                    merged_page = PyPDF2.PageObject.create_blank_page(
                        width=original_page.mediabox.width,
                        height=original_page.mediabox.height
                    )
                    merged_page.merge_page(original_page)
                    if overlay_pdf.pages:  # Check if overlay has pages before merging
                        merged_page.merge_page(overlay_pdf.pages[0])
                    
                    pdf_writer.add_page(merged_page)
                
                # Write the complete PDF
                with open(output_pdf, 'wb') as output_file:
                    pdf_writer.write(output_file)
                    
        except Exception as e:
            raise Exception(f"PDF Generation Error: {str(e)}")

    def generate_bubble_overlay(self):
        if not self.current_pdf_path:
            QMessageBox.warning(self, 'Error', 'No PDF loaded')
            return

        output_path, _ = QFileDialog.getSaveFileName(self, 'Save Bubble Overlay PDF', '', 'PDF Files (*.pdf)')
        if not output_path:
            return

        try:
            self.create_bubble_overlay(self.current_pdf_path, output_path)
            QMessageBox.information(self, 'Success', f'Bubble overlay saved to {output_path}')
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Failed to create bubble overlay: {str(e)}')

    # [Rest of the class methods remain the same]
    def load_pdf(self):
        pdf_path, _ = QFileDialog.getOpenFileName(self, 'Open PDF', '', 'PDF Files (*.pdf)')
        if pdf_path:
            self.current_pdf_path = pdf_path
            self.pdf_viewer.load_pdf(pdf_path)
            self.current_page_number = 0
            self.bubbles_by_page.clear()
            self.update_page_label()
            self.update_bubble_list()

    def prev_page(self):
        if self.current_pdf_path and self.current_page_number > 0:
            self.current_page_number -= 1
            self.pdf_viewer.show_page(self.current_page_number)
            self.update_page_label()
            self.update_bubble_list()

    def next_page(self):
        if self.current_pdf_path and self.current_page_number < self.pdf_viewer.total_pages - 1:
            self.current_page_number += 1
            self.pdf_viewer.show_page(self.current_page_number)
            self.update_page_label()
            self.update_bubble_list()

    def update_page_label(self):
        self.page_label.setText(f'Page: {self.current_page_number + 1}/{self.pdf_viewer.total_pages}')

def main():
    app = QApplication(sys.argv)
    ex = InteractivePDFBubblePlacer()
    ex.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()