# -*- coding: utf-8 -*-
"""
Created on Sun Feb  9 13:29:04 2025

@author: hendrik
"""

import pytesseract
from PIL import Image
import numpy as np

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

def process_image(image):
    """
    Process an image and return the OCR text
    
    Args:
        image: PIL Image object containing the region to process
        
    Returns:
        str: Extracted text from the image
    """
    try:
        # Preprocess image if needed
        # Convert to grayscale
        if image.mode != 'L':
            image = image.convert('L')
            image.show()
            
        # Optionally enhance image
        # image = image.point(lambda x: 0 if x < 128 else 255)  # Threshold
        
        # Perform OCR
        text = pytesseract.image_to_string(image)
        
        # Clean up text
        text = text.strip()
        
        print(text)
        return text
    except Exception as e:
        raise Exception(f"OCR processing failed: {str(e)}")

# Optional: Add more image preprocessing functions if needed
def enhance_image(image):
    """
    Enhance image for better OCR results
    
    Args:
        image: PIL Image object
        
    Returns:
        PIL Image: Enhanced image
    """
    # Convert to numpy array
    img_array = np.array(image)
    
    # Apply various enhancements
    # Example: Contrast stretching
    p2, p98 = np.percentile(img_array, (2, 98))
    img_array = np.interp(img_array, (p2, p98), (0, 255))
    
    # Convert back to PIL Image
    return Image.fromarray(img_array.astype(np.uint8))