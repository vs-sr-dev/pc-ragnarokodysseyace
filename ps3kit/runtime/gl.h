// ps3kit runtime — the OpenGL 4.5 core functions the renderer uses, loaded
// through SDL (video.cpp defines them and fills them in).
#pragma once
#include <GL/glcorearb.h>

#define PS3KIT_GL_FUNCS(X)                                                                          \
    X(PFNGLGETERRORPROC, glGetError)                                                                \
    X(PFNGLGETSTRINGPROC, glGetString)                                                              \
    X(PFNGLENABLEPROC, glEnable)                                                                    \
    X(PFNGLDISABLEPROC, glDisable)                                                                  \
    X(PFNGLVIEWPORTPROC, glViewport)                                                                \
    X(PFNGLSCISSORPROC, glScissor)                                                                  \
    X(PFNGLCOLORMASKPROC, glColorMask)                                                              \
    X(PFNGLDEPTHMASKPROC, glDepthMask)                                                              \
    X(PFNGLSTENCILMASKPROC, glStencilMask)                                                          \
    X(PFNGLPIXELSTOREIPROC, glPixelStorei)                                                          \
    X(PFNGLDEBUGMESSAGECALLBACKPROC, glDebugMessageCallback)                                        \
    X(PFNGLCREATETEXTURESPROC, glCreateTextures)                                                    \
    X(PFNGLTEXTURESTORAGE2DPROC, glTextureStorage2D)                                                \
    X(PFNGLTEXTURESUBIMAGE2DPROC, glTextureSubImage2D)                                              \
    X(PFNGLDELETETEXTURESPROC, glDeleteTextures)                                                    \
    X(PFNGLGETTEXTUREIMAGEPROC, glGetTextureImage)                                                  \
    X(PFNGLCREATEFRAMEBUFFERSPROC, glCreateFramebuffers)                                            \
    X(PFNGLDELETEFRAMEBUFFERSPROC, glDeleteFramebuffers)                                            \
    X(PFNGLNAMEDFRAMEBUFFERTEXTUREPROC, glNamedFramebufferTexture)                                  \
    X(PFNGLBINDFRAMEBUFFERPROC, glBindFramebuffer)                                                  \
    X(PFNGLBLITNAMEDFRAMEBUFFERPROC, glBlitNamedFramebuffer)                                        \
    X(PFNGLCHECKNAMEDFRAMEBUFFERSTATUSPROC, glCheckNamedFramebufferStatus)                          \
    X(PFNGLCLEARNAMEDFRAMEBUFFERFVPROC, glClearNamedFramebufferfv)                                  \
    X(PFNGLCLEARNAMEDFRAMEBUFFERFIPROC, glClearNamedFramebufferfi)

#define PS3KIT_GL_DECLARE(T, n) extern T n;
PS3KIT_GL_FUNCS(PS3KIT_GL_DECLARE)
#undef PS3KIT_GL_DECLARE
