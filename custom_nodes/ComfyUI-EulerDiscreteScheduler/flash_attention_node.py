"""
ComfyUI Custom Node: Patch Flash Attention 2

This node patches ComfyUI models to use Flash Attention 2 as the attention backend.
Flash Attention 2 provides optimized attention computation for compatible GPUs.

Based on the pattern from ComfyUI-KJNodes model optimization nodes.
"""

import torch
import logging

logger = logging.getLogger(__name__)

class PatchFlashAttention:
    """
    Patches a model to use Flash Attention 2 as the attention backend.
    
    Flash Attention 2 provides memory-efficient and faster attention computation
    for NVIDIA GPUs with Ampere, Ada, or Hopper architectures (RTX 30xx, 40xx, etc.).
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL",),
                "enabled": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "Enable or disable Flash Attention 2. When enabled, uses optimized attention kernels."
                }),
            },
            "optional": {
                "softmax_scale": ("FLOAT", {
                    "default": 0.0,
                    "min": 0.0,
                    "max": 10.0,
                    "step": 0.01,
                    "tooltip": "Softmax scale factor. Set to 0 for automatic scaling (1/sqrt(d)). Higher values increase attention sharpness."
                }),
                "causal": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "Use causal masking (for autoregressive models). Usually False for diffusion models."
                }),
                "window_size": ("INT", {
                    "default": -1,
                    "min": -1,
                    "max": 8192,
                    "tooltip": "Local attention window size. -1 for full attention. Positive values enable sliding window attention."
                }),
                "deterministic": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "Use deterministic implementation. May be slower but gives reproducible results."
                }),
                "debug": (["disabled", "enabled"], {
                    "default": "disabled",
                    "tooltip": "Enable verbose debug logging to console. Use 'enabled' to see detailed Flash Attention status messages."
                }),
            }
        }
    
    RETURN_TYPES = ("MODEL", "STRING",)
    RETURN_NAMES = ("model", "status",)
    FUNCTION = "patch"
    CATEGORY = "model_patches/attention"
    DESCRIPTION = "Patches model to use Flash Attention 2 for optimized attention computation. Requires flash_attn library installed and compatible GPU."
    
    def patch(self, model, enabled, softmax_scale=0.0, causal=False, window_size=-1, deterministic=False, debug="disabled"):
        # Clone the model to avoid modifying the original
        model_clone = model.clone()
        debug_enabled = (debug == "enabled")
        
        if not enabled:
            status_msg = "⚠️ Flash Attention 2 DISABLED - Using standard attention"
            if debug_enabled:
                print(f"\n{'='*60}")
                print(f"[Flash Attention 2] {status_msg}")
                print(f"{'='*60}\n")
            logger.info("Flash Attention 2 is disabled, returning original model")
            return (model_clone, status_msg)
        
        # Check if flash_attn is available
        try:
            from flash_attn import flash_attn_func, flash_attn_varlen_func
            flash_attn_available = True
            if debug_enabled:
                print(f"\n{'='*60}")
                print(f"[Flash Attention 2] ✅ Library found and loaded successfully!")
                print(f"{'='*60}")
        except ImportError as e:
            status_msg = "❌ FAILED: flash_attn library not installed"
            # Always show critical errors even without debug
            print(f"\n{'='*60}")
            print(f"[Flash Attention 2] {status_msg}")
            print(f"[Flash Attention 2] Install with: pip install flash-attn")
            if debug_enabled:
                print(f"[Flash Attention 2] Error: {e}")
            print(f"{'='*60}\n")
            logger.warning(
                "flash_attn library not found. Flash Attention 2 cannot be enabled. "
                "Install with: pip install flash-attn"
            )
            return (model_clone, status_msg)
        
        # Prepare configuration for flash attention
        flash_config = {
            "softmax_scale": softmax_scale if softmax_scale > 0 else None,
            "causal": causal,
            "window_size": (-1, -1) if window_size == -1 else (window_size, window_size),
            "deterministic": deterministic,
        }
        
        # Create the patching function
        def flash_attention_forward(q, k, v, extra_options=None):
            """
            Flash Attention 2 forward function.
            
            Args:
                q: Query tensor [batch, seq_len, num_heads, head_dim]
                k: Key tensor [batch, seq_len, num_heads, head_dim]
                v: Value tensor [batch, seq_len, num_heads, head_dim]
                extra_options: Additional options (mask, etc.)
            
            Returns:
                Attention output tensor
            """
            # Log first few calls to verify Flash Attention is being used (only in debug mode)
            if flash_attention_forward._debug_enabled:
                flash_attention_forward._call_count += 1
                if flash_attention_forward._call_count <= 2:
                    print(f"[Flash Attention 2] 🔄 Attention call #{flash_attention_forward._call_count} - Using Flash Attention kernel")
            
            # Flash attention expects input shape: [batch, seq_len, num_heads, head_dim]
            # Ensure tensors are contiguous and in the right format
            q = q.contiguous()
            k = k.contiguous()
            v = v.contiguous()
            
            # Get softmax scale
            scale = flash_config["softmax_scale"]
            if scale is None:
                head_dim = q.shape[-1]
                scale = 1.0 / (head_dim ** 0.5)
            
            # Apply flash attention
            try:
                output = flash_attn_func(
                    q, k, v,
                    softmax_scale=scale,
                    causal=flash_config["causal"],
                    window_size=flash_config["window_size"],
                    deterministic=flash_config["deterministic"],
                )
                return output
            except Exception as e:
                error_msg = f"Flash Attention 2 runtime error: {e}. Falling back to standard attention."
                # Always show runtime errors even without debug
                print(f"\n[Flash Attention 2] ⚠️ {error_msg}\n")
                logger.error(error_msg)
                # Fallback to standard attention
                return torch.nn.functional.scaled_dot_product_attention(
                    q.transpose(1, 2), 
                    k.transpose(1, 2), 
                    v.transpose(1, 2),
                    scale=scale
                ).transpose(1, 2)
        
        # Initialize function attributes after definition
        flash_attention_forward._call_count = 0
        flash_attention_forward._debug_enabled = debug_enabled
        
        # Apply the patch to the model
        # We need to patch all attention blocks in the model
        try:
            # Get the model's attention block configuration
            # We'll patch both input and output blocks
            patched_count = 0
            
            # Patch input blocks
            if hasattr(model_clone.model, 'diffusion_model') and hasattr(model_clone.model.diffusion_model, 'input_blocks'):
                num_input_blocks = len(model_clone.model.diffusion_model.input_blocks)
                for i in range(num_input_blocks):
                    model_clone.set_model_attn2_replace(flash_attention_forward, "input", i)
                    patched_count += 1
            
            # Patch middle block
            if hasattr(model_clone.model, 'diffusion_model') and hasattr(model_clone.model.diffusion_model, 'middle_block'):
                model_clone.set_model_attn2_replace(flash_attention_forward, "middle", 0)
                patched_count += 1
            
            # Patch output blocks
            if hasattr(model_clone.model, 'diffusion_model') and hasattr(model_clone.model.diffusion_model, 'output_blocks'):
                num_output_blocks = len(model_clone.model.diffusion_model.output_blocks)
                for i in range(num_output_blocks):
                    model_clone.set_model_attn2_replace(flash_attention_forward, "output", i)
                    patched_count += 1
            
            status_msg = (
                f"✅ Flash Attention 2 ENABLED\n"
                f"  • Patched blocks: {patched_count}\n"
                f"  • Softmax scale: {flash_config['softmax_scale'] or 'auto (1/√d)'}\n"
                f"  • Causal: {flash_config['causal']}\n"
                f"  • Window size: {flash_config['window_size']}\n"
                f"  • Deterministic: {flash_config['deterministic']}"
            )
            
            if debug_enabled:
                print(f"\n{'='*60}")
                print(f"[Flash Attention 2] ✅ SUCCESSFULLY PATCHED MODEL")
                print(f"{'='*60}")
                print(f"  Patched {patched_count} attention blocks")
                print(f"  Configuration:")
                print(f"    Softmax scale:  {flash_config['softmax_scale'] or 'auto (1/√d)'}")
                print(f"    Causal:         {flash_config['causal']}")
                print(f"    Window size:    {flash_config['window_size']}")
                print(f"    Deterministic:  {flash_config['deterministic']}")
                print(f"{'='*60}")
                print(f"  💡 Watch for any attention-related errors during inference.")
                print(f"  💡 If errors occur, the node will auto-fallback to standard attention.")
                print(f"  💡 Compatible GPUs: RTX 30xx/40xx, A100, H100")
                print(f"{'='*60}\n")
            
            logger.info(
                f"Flash Attention 2 patched successfully: {patched_count} blocks with config: "
                f"softmax_scale={flash_config['softmax_scale']}, "
                f"causal={flash_config['causal']}, "
                f"window_size={flash_config['window_size']}, "
                f"deterministic={flash_config['deterministic']}"
            )
        except Exception as e:
            status_msg = f"❌ FAILED: Could not patch model - {str(e)}"
            # Always show critical patching errors
            print(f"\n{'='*60}")
            print(f"[Flash Attention 2] {status_msg}")
            print(f"{'='*60}\n")
            logger.error(f"Failed to patch model with Flash Attention 2: {e}")
            logger.info("Returning unpatched model")
        
        return (model_clone, status_msg)


# Node registration for ComfyUI
NODE_CLASS_MAPPINGS = {
    "PatchFlashAttention": PatchFlashAttention
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "PatchFlashAttention": "Patch Flash Attention 2"
}
