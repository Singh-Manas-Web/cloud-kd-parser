"""Prompt format, model loading and greedy generation. Shared by the service, training and evaluation."""
import os

PROMPT_TEMPLATE = "Command: {text}\nJSON:"


def format_prompt(text):
    """The exact input the student sees, in training and at inference."""
    return PROMPT_TEMPLATE.format(text=" ".join(str(text).split()))


def trim_output(text):
    """Keep the generated text up to and including the first closing brace (our stop rule)."""
    text = text.strip()
    end = text.find("}")
    return text[: end + 1] if end != -1 else text


class Parser:
    def __init__(self, model_dir, max_new_tokens=64, threads=None, revision=None):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer, StoppingCriteria

        if threads:
            torch.set_num_threads(int(threads))
        self.torch = torch
        kwargs = {"revision": revision} if revision else {}
        self.tok = AutoTokenizer.from_pretrained(model_dir, **kwargs)
        self.model = AutoModelForCausalLM.from_pretrained(model_dir, torch_dtype=torch.float32, **kwargs)
        self.model.eval()
        self.max_new_tokens = int(max_new_tokens)
        tok = self.tok

        class BraceStop(StoppingCriteria):
            """Stop as soon as the newest token contains '}' (the end of the JSON object)."""

            def __init__(self, prompt_len):
                self.prompt_len = prompt_len

            def __call__(self, input_ids, scores, **kwargs):
                done = input_ids.shape[1] > self.prompt_len and "}" in tok.decode(input_ids[0, -1:])
                return torch.full((input_ids.shape[0],), bool(done), dtype=torch.bool, device=input_ids.device)

        self._stop_cls = BraceStop

    def generate(self, text):
        from transformers import StoppingCriteriaList

        enc = self.tok(format_prompt(text), return_tensors="pt")
        n = enc["input_ids"].shape[1]
        with self.torch.inference_mode():
            out = self.model.generate(
                **enc,
                max_new_tokens=self.max_new_tokens,
                do_sample=False,
                num_beams=1,
                pad_token_id=self.tok.eos_token_id,
                eos_token_id=self.tok.eos_token_id,
                stopping_criteria=StoppingCriteriaList([self._stop_cls(n)]),
            )
        return trim_output(self.tok.decode(out[0, n:], skip_special_tokens=True))


def default_threads():
    return int(os.environ.get("TORCH_THREADS", "1"))
