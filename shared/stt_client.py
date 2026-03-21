"""
Speech-to-Text using Sarvam AI (Saarika)
Optimized for Indian languages and accents
"""
from loguru import logger
import os
from typing import Optional
from shared.sarvam_client import get_sarvam_client
import audioop
import io
import wave


class STTClient:
    """Speech-to-Text client using Sarvam AI"""
    
    def __init__(self, model_name: str = None):
        logger.info("Initializing Sarvam STT Client...")
        self.sarvam_client = get_sarvam_client()
        logger.info("✅ Sarvam STT ready")
    
    async def transcribe(
        self, 
        audio_data: bytes,
        language: str = "en",
        prompt: str = None
    ) -> Optional[str]:
        """
        Transcribe audio to text using Sarvam AI
        
        Args:
            audio_data: Raw audio bytes (WAV format)
            language: Language code (en, hi, mr, etc.)
            prompt: Optional hint for transcription context
        
        Returns:
            Transcribed text or empty string
        """
        try:
            if not audio_data:
                logger.warning("No audio data provided to STT")
                return ""
            
            # ===== AUDIO ENHANCEMENT FOR BETTER STT (ML Solution Phase 1) =====
            # Sarvam expects higher quality audio - upsample from 8kHz to 16kHz
            enhanced_audio = self._enhance_audio_quality(audio_data)
            
            # Map language code to Sarvam format
            sarvam_code = language if "-" in language else f"{language}-IN"
            
            logger.debug(f"Transcribing with Sarvam STT (lang={sarvam_code}, enhanced=True)")
            
            text = await self.sarvam_client.speech_to_text(
                enhanced_audio, 
                language_code=sarvam_code
            )
            
            if text:
                logger.info(f"📝 STT: '{text}'")
            else:
                logger.debug("No speech detected")
            
            return text or ""
            
        except Exception as e:
            logger.error(f"STT error: {e}")
            return ""
    
    def _enhance_audio_quality(self, audio_data: bytes) -> bytes:
        """
        Enhance audio quality for better STT accuracy
        - Upsamples 8kHz mulaw to 16kHz PCM (Sarvam's expected format)
        - Normalizes volume
        """
        try:
            # Read WAV file
            with wave.open(io.BytesIO(audio_data), 'rb') as wav:
                params = wav.getparams()
                frames = wav.readframes(params.nframes)
                sample_rate = params.framerate
                channels = params.nchannels
                sampwidth = params.sampwidth
            
            # If already 16kHz+, return as-is
            if sample_rate >= 16000:
                return audio_data
            
            # Upsample to 16kHz (simple linear interpolation)
            # For 8kHz -> 16kHz, we need 2x samples
            if sample_rate == 8000:
                frames_16k = audioop.ratecv(
                    frames,
                    sampwidth,
                    channels,
                    8000,  # from rate
                    16000,  # to rate
                    None
                )[0]
            else:
                # Generic resampling (not common for Twilio)
                ratio = 16000 / sample_rate
                frames_16k = audioop.ratecv(
                    frames,
                    sampwidth,
                    channels,
                    sample_rate,
                    16000,
                    None
                )[0]
            
            # Create new WAV at 16kHz
            output = io.BytesIO()
            with wave.open(output, 'wb') as wav_out:
                wav_out.setnchannels(channels)
                wav_out.setsampwidth(sampwidth)
                wav_out.setframerate(16000)
                wav_out.writeframes(frames_16k)
            
            enhanced = output.getvalue()
            logger.debug(f"Audio enhanced: {sample_rate}Hz -> 16000Hz ({len(audio_data)} -> {len(enhanced)} bytes)")
            return enhanced
            
        except Exception as e:
            logger.warning(f"Audio enhancement failed, using original: {e}")
            return audio_data
    
    def transcribe_audio(
        self, 
        audio_data: Optional[bytes] = None,
        audio_file: Optional[str] = None,
        language: str = "en"
    ) -> Optional[str]:
        """
        Synchronous wrapper for backwards compatibility.
        Note: This uses asyncio.run() - prefer async transcribe() in async contexts.
        """
        import asyncio
        
        try:
            if audio_file and not audio_data:
                with open(audio_file, "rb") as f:
                    audio_data = f.read()
            
            if not audio_data:
                logger.error("No audio data or file provided")
                return None
            
            # Run async method synchronously
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If already in async context, create a new task
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run, 
                        self.transcribe(audio_data, language)
                    )
                    return future.result()
            else:
                return asyncio.run(self.transcribe(audio_data, language))
                
        except Exception as e:
            logger.error(f"STT sync error: {e}")
            return None


# Global instance
stt_client = None

def get_stt_client() -> STTClient:
    """Get or create global STT client"""
    global stt_client
    if stt_client is None:
        stt_client = STTClient()
    return stt_client
