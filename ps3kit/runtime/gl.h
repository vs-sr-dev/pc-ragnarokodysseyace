// ps3kit runtime — the OpenGL 4.5 core functions the renderer uses, loaded
// through SDL (video.cpp defines them and fills them in).
#pragma once
#include <GL/glcorearb.h>

#define PS3KIT_GL_FUNCS(X)                                                                          \
    X(PFNGLGETERRORPROC, glGetError)                                                                \
    X(PFNGLGETSTRINGPROC, glGetString)                                                              \
    X(PFNGLENABLEPROC, glEnable)                                                                    \
    X(PFNGLDISABLEPROC, glDisable)                                                                  \
    X(PFNGLENABLEIPROC, glEnablei)                                                                  \
    X(PFNGLDISABLEIPROC, glDisablei)                                                                \
    X(PFNGLVIEWPORTPROC, glViewport)                                                                \
    X(PFNGLFINISHPROC, glFinish)                                                                    \
    X(PFNGLSCISSORPROC, glScissor)                                                                  \
    X(PFNGLCOLORMASKPROC, glColorMask)                                                              \
    X(PFNGLCOLORMASKIPROC, glColorMaski)                                                            \
    X(PFNGLDEPTHMASKPROC, glDepthMask)                                                              \
    X(PFNGLDEPTHFUNCPROC, glDepthFunc)                                                              \
    X(PFNGLSTENCILMASKPROC, glStencilMask)                                                          \
    X(PFNGLSTENCILMASKSEPARATEPROC, glStencilMaskSeparate)                                          \
    X(PFNGLSTENCILFUNCSEPARATEPROC, glStencilFuncSeparate)                                          \
    X(PFNGLSTENCILOPSEPARATEPROC, glStencilOpSeparate)                                              \
    X(PFNGLBLENDFUNCSEPARATEPROC, glBlendFuncSeparate)                                              \
    X(PFNGLBLENDEQUATIONSEPARATEPROC, glBlendEquationSeparate)                                      \
    X(PFNGLBLENDCOLORPROC, glBlendColor)                                                            \
    X(PFNGLLOGICOPPROC, glLogicOp)                                                                  \
    X(PFNGLCULLFACEPROC, glCullFace)                                                                \
    X(PFNGLFRONTFACEPROC, glFrontFace)                                                              \
    X(PFNGLPOLYGONMODEPROC, glPolygonMode)                                                          \
    X(PFNGLPOINTSIZEPROC, glPointSize)                                                              \
    X(PFNGLCLIPCONTROLPROC, glClipControl)                                                          \
    X(PFNGLPIXELSTOREIPROC, glPixelStorei)                                                          \
    X(PFNGLDEBUGMESSAGECALLBACKPROC, glDebugMessageCallback)                                        \
    X(PFNGLDRAWARRAYSPROC, glDrawArrays)                                                            \
    X(PFNGLMULTIDRAWARRAYSPROC, glMultiDrawArrays)                                                  \
    X(PFNGLDRAWELEMENTSPROC, glDrawElements)                                                        \
    X(PFNGLCREATESHADERPROC, glCreateShader)                                                        \
    X(PFNGLSHADERSOURCEPROC, glShaderSource)                                                        \
    X(PFNGLCOMPILESHADERPROC, glCompileShader)                                                      \
    X(PFNGLGETSHADERIVPROC, glGetShaderiv)                                                          \
    X(PFNGLGETSHADERINFOLOGPROC, glGetShaderInfoLog)                                                \
    X(PFNGLDELETESHADERPROC, glDeleteShader)                                                        \
    X(PFNGLCREATEPROGRAMPROC, glCreateProgram)                                                      \
    X(PFNGLATTACHSHADERPROC, glAttachShader)                                                        \
    X(PFNGLLINKPROGRAMPROC, glLinkProgram)                                                          \
    X(PFNGLGETPROGRAMIVPROC, glGetProgramiv)                                                        \
    X(PFNGLGETPROGRAMINFOLOGPROC, glGetProgramInfoLog)                                              \
    X(PFNGLUSEPROGRAMPROC, glUseProgram)                                                            \
    X(PFNGLGETUNIFORMLOCATIONPROC, glGetUniformLocation)                                            \
    X(PFNGLPROGRAMUNIFORM4FVPROC, glProgramUniform4fv)                                              \
    X(PFNGLPROGRAMUNIFORM4FPROC, glProgramUniform4f)                                                \
    X(PFNGLPROGRAMUNIFORM4IPROC, glProgramUniform4i)                                                \
    X(PFNGLPROGRAMUNIFORM1FPROC, glProgramUniform1f)                                                \
    X(PFNGLPROGRAMUNIFORM1UIPROC, glProgramUniform1ui)                                              \
    X(PFNGLCREATEBUFFERSPROC, glCreateBuffers)                                                      \
    X(PFNGLNAMEDBUFFERSTORAGEPROC, glNamedBufferStorage)                                            \
    X(PFNGLNAMEDBUFFERSUBDATAPROC, glNamedBufferSubData)                                            \
    X(PFNGLINVALIDATEBUFFERDATAPROC, glInvalidateBufferData)                                        \
    X(PFNGLCREATEVERTEXARRAYSPROC, glCreateVertexArrays)                                            \
    X(PFNGLBINDVERTEXARRAYPROC, glBindVertexArray)                                                  \
    X(PFNGLVERTEXARRAYVERTEXBUFFERPROC, glVertexArrayVertexBuffer)                                  \
    X(PFNGLVERTEXARRAYBINDINGDIVISORPROC, glVertexArrayBindingDivisor)                              \
    X(PFNGLVERTEXARRAYELEMENTBUFFERPROC, glVertexArrayElementBuffer)                                \
    X(PFNGLENABLEVERTEXARRAYATTRIBPROC, glEnableVertexArrayAttrib)                                  \
    X(PFNGLDISABLEVERTEXARRAYATTRIBPROC, glDisableVertexArrayAttrib)                                \
    X(PFNGLVERTEXARRAYATTRIBFORMATPROC, glVertexArrayAttribFormat)                                  \
    X(PFNGLVERTEXARRAYATTRIBBINDINGPROC, glVertexArrayAttribBinding)                                \
    X(PFNGLVERTEXATTRIB4FPROC, glVertexAttrib4f)                                                    \
    X(PFNGLCREATETEXTURESPROC, glCreateTextures)                                                    \
    X(PFNGLTEXTURESTORAGE1DPROC, glTextureStorage1D)                                                \
    X(PFNGLTEXTURESTORAGE2DPROC, glTextureStorage2D)                                                \
    X(PFNGLTEXTURESTORAGE3DPROC, glTextureStorage3D)                                                \
    X(PFNGLTEXTURESUBIMAGE1DPROC, glTextureSubImage1D)                                              \
    X(PFNGLTEXTURESUBIMAGE2DPROC, glTextureSubImage2D)                                              \
    X(PFNGLTEXTURESUBIMAGE3DPROC, glTextureSubImage3D)                                              \
    X(PFNGLCOMPRESSEDTEXTURESUBIMAGE2DPROC, glCompressedTextureSubImage2D)                          \
    X(PFNGLCOMPRESSEDTEXTURESUBIMAGE3DPROC, glCompressedTextureSubImage3D)                          \
    X(PFNGLTEXTUREPARAMETERIPROC, glTextureParameteri)                                              \
    X(PFNGLBINDTEXTUREUNITPROC, glBindTextureUnit)                                                  \
    X(PFNGLDELETETEXTURESPROC, glDeleteTextures)                                                    \
    X(PFNGLGETTEXTUREIMAGEPROC, glGetTextureImage)                                                  \
    X(PFNGLCREATESAMPLERSPROC, glCreateSamplers)                                                    \
    X(PFNGLSAMPLERPARAMETERIPROC, glSamplerParameteri)                                              \
    X(PFNGLSAMPLERPARAMETERFPROC, glSamplerParameterf)                                              \
    X(PFNGLSAMPLERPARAMETERFVPROC, glSamplerParameterfv)                                            \
    X(PFNGLBINDSAMPLERPROC, glBindSampler)                                                          \
    X(PFNGLCREATEFRAMEBUFFERSPROC, glCreateFramebuffers)                                            \
    X(PFNGLDELETEFRAMEBUFFERSPROC, glDeleteFramebuffers)                                            \
    X(PFNGLNAMEDFRAMEBUFFERTEXTUREPROC, glNamedFramebufferTexture)                                  \
    X(PFNGLNAMEDFRAMEBUFFERDRAWBUFFERSPROC, glNamedFramebufferDrawBuffers)                          \
    X(PFNGLBINDFRAMEBUFFERPROC, glBindFramebuffer)                                                  \
    X(PFNGLBLITNAMEDFRAMEBUFFERPROC, glBlitNamedFramebuffer)                                        \
    X(PFNGLCHECKNAMEDFRAMEBUFFERSTATUSPROC, glCheckNamedFramebufferStatus)                          \
    X(PFNGLCLEARNAMEDFRAMEBUFFERFVPROC, glClearNamedFramebufferfv)                                  \
    X(PFNGLCLEARNAMEDFRAMEBUFFERFIPROC, glClearNamedFramebufferfi)

#define PS3KIT_GL_DECLARE(T, n) extern T n;
PS3KIT_GL_FUNCS(PS3KIT_GL_DECLARE)
#undef PS3KIT_GL_DECLARE
