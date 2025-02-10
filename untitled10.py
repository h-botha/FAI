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
from PyQt5.QtCore import Qt, QPoint, QRect, QRectF
import numpy as np
from PIL import Image
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
        self.zoom = 2
        self.scale_factor = 1
        
        # Selection variables
        self.selecting = False
        self.selection_start = None
        self.selection_end = None
        self.current_bubble = None
        
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.setWidget(self.image_label)
        self.setWidgetResizable(True)
        self.image_label.setMouseTracking(True)
        
        # Override mouse events
        self.image_label.mousePressEvent = self.on_mouse_press
        self.image_label.mouseMoveEvent = self.on_mouse_move
        self.image_label.mouseReleaseEvent = self.on_mouse_release
    
    def draw_bubbles_on_pixmap(self, painter):
        """Draw all bubbles for the current page on the pixmap"""
        current_page_bubbles = self.parent.get_bubbles_for_page(self.parent.current_page_number)
        previous_bubbles_count = self.parent.get_bubble_count_before_page(self.parent.current_page_number)
        
        pen = QPen(QColor(255, 0, 0))
        pen.setWidth(1)
        painter.setPen(pen)
        
        font = QFont()
        font.setPointSize(8)
        painter.setFont(font)
        
        for idx, (x, y) in enumerate(current_page_bubbles, previous_bubbles_count + 1):
            # Convert PDF coordinates to display coordinates
            display_x = x * self.scale_factor
            display_y = y * self.scale_factor
            
            # Draw bubble
            painter.drawEllipse(QPoint(int(display_x), int(display_y)), 5, 5)
            painter.drawText(QPoint(int(display_x-3), int(display_y+3)), str(idx))

    def display_pixmap_with_bubbles(self, pixmap):
        """Display the pixmap with bubbles and current selection"""
        display_pixmap = pixmap.copy()
        painter = QPainter(display_pixmap)
        
        # Draw existing bubbles
        self.draw_bubbles_on_pixmap(painter)
        
        # Draw current selection if active
        if self.selecting and self.selection_start and self.selection_end:
            painter.setPen(QPen(QColor(0, 0, 255), 0))
            selection_rect = QRect(self.selection_start, self.selection_end).normalized()
            painter.drawRect(selection_rect)
        
        painter.end()
        self.image_label.setPixmap(display_pixmap)
    
    def on_mouse_press(self, event):
        if event.button() == Qt.LeftButton:
            if self.parent.selection_mode:
                # Start selection
                self.selecting = True
                self.release_flag = False
                self.selection_start = event.pos()
                self.selection_end = event.pos()
                self.current_bubble = self.parent.get_current_bubble()
            else:
                # Add bubble
                self.add_bubble(event.pos())
        
    def on_mouse_move(self, event):
        if self.selecting and self.selection_start:
            self.selection_end = event.pos()
            if self.release_flag:
                self.update_selection()

    def on_mouse_release(self, event):
        if self.selecting and self.selection_start and self.selection_end:
            self.capture_selection()
            self.selecting = False
            self.selection_start = None
            self.selection_end = None
            self.release_flag = True
            self.update_selection()
    
    def update_selection(self):
        if self.image_label.pixmap():
            pixmap = self.image_label.pixmap().copy()
            painter = QPainter(pixmap)
            
            if self.selection_start and self.selection_end:
                # Draw selection rectangle
                painter.setPen(QPen(QColor(0, 0, 255), 2))
                selection_rect = QRect(self.selection_start, self.selection_end).normalized()
                painter.drawRect(selection_rect)
            
            # Draw bubbles
            self.draw_bubbles_on_pixmap(painter)

            painter.end()
            self.image_label.setPixmap(pixmap)

    def capture_selection(self):
        if not self.selection_start or not self.selection_end or not self.current_bubble:
            return
            
        # Get selection rectangle in display coordinates
        rect = QRect(self.selection_start, self.selection_end).normalized()
        
        # Convert to PDF coordinates
        pdf_rect = QRectF(
            rect.x() / self.scale_factor,
            rect.y() / self.scale_factor,
            rect.width() / self.scale_factor,
            rect.height() / self.scale_factor
        )
        
        # Capture the selected region
        pixmap = self.image_label.pixmap()
        if pixmap:
            # Get the selection as a QPixmap
            selection_image = pixmap.copy(rect)
            
            # Convert QPixmap to QImage
            qimage = selection_image.toImage()
            
            # Convert QImage to PIL Image
            width = qimage.width()
            height = qimage.height()
            ptr = qimage.bits()
            ptr.setsize(height * width * 4)  # 4 bytes per pixel for RGBA
            arr = np.frombuffer(ptr, np.uint8).reshape((height, width, 4))  # 4 channels (RGBA)
            
            # Convert to RGB PIL Image
            image = Image.fromarray(arr, 'RGBA').convert('RGB')
            
            # Save region info and image
            self.parent.add_region_to_bubble(
                self.current_bubble,
                {
                    'rect': pdf_rect,
                    'page': self.parent.current_page_number,
                    'image': image
                }
            )
            
            # Process OCR in separate thread
            self.parent.process_ocr(image, self.current_bubble)
    
    def add_bubble(self, pos):
        display_x = pos.x()
        display_y = pos.y()
        
        # Convert to PDF coordinates
        pdf_x = display_x / self.scale_factor
        pdf_y = display_y / self.scale_factor
        
        self.parent.add_bubble_position(pdf_x, pdf_y)

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

    def display_current_page_bubbles(self):
        if self.image_label.pixmap():
            self.display_pixmap_with_bubbles(self.image_label.pixmap())

class InteractivePDFBubblePlacer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.current_pdf_path = None
        self.bubbles_by_page = {}
        self.current_page_number = 0
        self.selection_mode = False
        self.bubble_regions = {}  # Store selected regions for each bubble
        self.bubble_text = {}     # Store OCR text for each bubble

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
        
        self.select_mode_btn = QPushButton('Toggle Selection Mode')
        self.select_mode_btn.setCheckable(True)
        self.select_mode_btn.clicked.connect(self.toggle_selection_mode)
        control_layout.addWidget(self.select_mode_btn)
        
    def toggle_selection_mode(self):
        self.selection_mode = self.select_mode_btn.isChecked()

    def get_current_bubble(self):
        """Get the last bubble on the current page"""
        page_bubbles = self.bubbles_by_page.get(self.current_page_number, [])
        if page_bubbles:
            return (self.current_page_number, len(page_bubbles) - 1)
        return None
    
    def add_region_to_bubble(self, bubble_id, region_info):
        if bubble_id:
            self.bubble_regions[bubble_id] = region_info

    def process_ocr(self, image, bubble_id):
        """Send image to OCR module and store result"""
        try:
            from ocr_module import process_image
            text = process_image(image)
            self.bubble_text[bubble_id] = text
            self.update_bubble_list()
        except Exception as e:
            QMessageBox.warning(self, 'OCR Error', f'Failed to process text: {str(e)}')

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
        bubble_text = 'Bubble Positions and Text:\n'
        total_count = 0
        
        if not self.bubbles_by_page:
            self.bubble_list.setText(bubble_text)
            return
            
        max_page = max(self.bubbles_by_page.keys())
        
        for page in range(max_page + 1):
            page_bubbles = self.bubbles_by_page.get(page, [])
            if page_bubbles:
                bubble_text += f'\nPage {page + 1}:\n'
                for i, (x, y) in enumerate(page_bubbles, total_count + 1):
                    bubble_text += f'{i}: ({x:.2f}, {y:.2f})'
                    bubble_id = (page, i-total_count-1)
                    if bubble_id in self.bubble_text:
                        bubble_text += f' - Text: {self.bubble_text[bubble_id]}'
                    bubble_text += '\n'
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