from services.phonefmt import apply_reformatting

class ReformatService:
  def run(self, text: str, locale: str):
    return apply_reformatting(text, locale)  # -> (final_message, meta)
