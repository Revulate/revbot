import re

def split_message(message: str, max_length: int = 500) -> list:
    """
    Splits a message into chunks that fit within the specified max_length.
    Ensures that sentences are split only at word boundaries.
    """
    words = message.split()  # Split by spaces instead of sentences
    chunks = []
    current_chunk = ""

    for word in words:
        # Check if adding the next word exceeds max_length
        if len(current_chunk) + len(word) + 1 <= max_length:
            if current_chunk:
                current_chunk += " " + word
            else:
                current_chunk = word
        else:
            # Save the current chunk and start a new one
            chunks.append(current_chunk)
            current_chunk = word
    
    # Append the last chunk if not empty
    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def remove_duplicate_sentences(text: str) -> str:
    """
    Removes duplicate sentences from the provided text.

    Parameters:
        text (str): The input text to remove duplicates from.

    Returns:
        str: Text with duplicate sentences removed.
    """
    # Split the text into sentences based on punctuation followed by spaces
    sentences = re.split(r'(?<=[.!?]) +', text)
    seen = set()
    unique_sentences = []
    
    for sentence in sentences:
        # Normalize by stripping extra spaces and lowercasing
        normalized = sentence.strip().lower()
        
        # Only add sentence if it hasn't been seen before
        if normalized not in seen:
            unique_sentences.append(sentence.strip())
            seen.add(normalized)
    
    # Return the text with unique sentences only
    return ' '.join(unique_sentences)
