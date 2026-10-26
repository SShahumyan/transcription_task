"""Armenian -> English text translation with NLLB-200 running on CTranslate2."""

import ctranslate2
from huggingface_hub import snapshot_download
from transformers import AutoTokenizer

# Pre-converted CTranslate2 checkpoints, so no PyTorch is needed at runtime.
MT_MODELS = {
    "600m": "pulkitchowdry/nllb-600m-ct2-int8",
    "1.3b": "michaelfeil/ct2fast-nllb-200-distilled-1.3B",
}

SRC_LANG = "hye_Armn"
TGT_LANG = "eng_Latn"


class Translator:
    def __init__(self, size: str = "600m", threads: int = 0, beam_size: int = 2):
        model_dir = snapshot_download(MT_MODELS[size])
        self.translator = ctranslate2.Translator(
            model_dir, device="cpu", compute_type="int8", intra_threads=threads
        )
        self.tokenizer = AutoTokenizer.from_pretrained(model_dir, src_lang=SRC_LANG)
        self.beam_size = beam_size

    def translate(self, text: str) -> str:
        if not text.strip():
            return ""
        source = self.tokenizer.convert_ids_to_tokens(self.tokenizer.encode(text))
        result = self.translator.translate_batch(
            [source], target_prefix=[[TGT_LANG]], beam_size=self.beam_size
        )
        target = result[0].hypotheses[0][1:]  # drop the target-language token
        return self.tokenizer.decode(self.tokenizer.convert_tokens_to_ids(target))
