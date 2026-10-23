#!/usr/bin/env python3
"""Regenerate the checked-in Xcode project without third-party dependencies."""
from pathlib import Path
import hashlib
import json
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
objects = {}

def uid(name):
    return hashlib.sha1(name.encode()).hexdigest()[:24].upper()

def add(identity, isa, **properties):
    key = uid(identity)
    objects[key] = dict(isa=isa, **properties)
    return key

def ref(path, kind='sourcecode.swift', tree='<group>'):
    return add('file:' + path, 'PBXFileReference', lastKnownFileType=kind, path=path, sourceTree=tree)

shared = [p.relative_to(ROOT).as_posix() for p in sorted((ROOT / 'Shared').glob('*.swift'))]
app = [p.relative_to(ROOT).as_posix() for p in sorted((ROOT / 'App').glob('*.swift'))]
widgets = ['Widgets/BoulderbatWidgets.swift']
watch = ['Watch/BoulderbatWatchApp.swift', 'App/AppStore.swift']
source_refs = {p: ref(p) for p in dict.fromkeys(shared + app + widgets + watch)}
assets = ref('Resources/Assets.xcassets', 'folder.assetcatalog')
config_refs = [ref(p.relative_to(ROOT).as_posix(), 'text.plist.xml') for p in sorted((ROOT / 'Configuration').glob('*'))]
groups = []
for folder in ['Shared', 'App', 'Widgets', 'Watch']:
    groups.append(add('group:' + folder, 'PBXGroup', name=folder, children=[v for p,v in source_refs.items() if p.startswith(folder + '/')], sourceTree='<group>'))
groups += [add('group:Resources', 'PBXGroup', name='Resources', children=[assets], sourceTree='<group>'),
           add('group:Configuration', 'PBXGroup', name='Configuration', children=config_refs, sourceTree='<group>')]
products = {}
for name in ['Boulderbat', 'BoulderbatWidgets', 'BoulderbatWatch', 'BoulderbatWatchWidgets']:
    widget = name.endswith('Widgets')
    products[name] = add('product:' + name, 'PBXFileReference', explicitFileType='wrapper.app-extension' if widget else 'wrapper.application', includeInIndex=0, path=name + ('.appex' if widget else '.app'), sourceTree='BUILT_PRODUCTS_DIR')
products_group = add('group:Products', 'PBXGroup', name='Products', children=list(products.values()), sourceTree='<group>')
main_group = add('group:Main', 'PBXGroup', children=groups + [products_group], sourceTree='<group>')

base = dict(SWIFT_VERSION='5.0', CLANG_ENABLE_MODULES='YES', CLANG_ENABLE_OBJC_ARC='YES',
            MARKETING_VERSION='1.0', CURRENT_PROJECT_VERSION='5', CODE_SIGN_STYLE='Automatic',
            IPHONEOS_DEPLOYMENT_TARGET='17.0', MACOSX_DEPLOYMENT_TARGET='14.0',
            WATCHOS_DEPLOYMENT_TARGET='10.0', XROS_DEPLOYMENT_TARGET='26.0',
            ENABLE_USER_SCRIPT_SANDBOXING='YES', GENERATE_INFOPLIST_FILE='NO',
            SWIFT_STRICT_CONCURRENCY='targeted', DEVELOPMENT_TEAM='',
            ASSETCATALOG_COMPILER_GLOBAL_ACCENT_COLOR_NAME='AccentColor')

def configuration_list(name, settings):
    configs = []
    for variant in ['Debug', 'Release']:
        config = dict(settings)
        config['SWIFT_OPTIMIZATION_LEVEL'] = '-Onone' if variant == 'Debug' else '-O'
        config['DEBUG_INFORMATION_FORMAT'] = 'dwarf' if variant == 'Debug' else 'dwarf-with-dsym'
        config['SWIFT_ACTIVE_COMPILATION_CONDITIONS'] = 'DEBUG' if variant == 'Debug' else ''
        if name == 'project':
            config['BOULDERBAT_APP_BUNDLE_IDENTIFIER'] = 'dev.flofriday.boulderbat' + ('.debug' if variant == 'Debug' else '')
            config['BOULDERBAT_URL_SCHEME'] = 'boulderbat-debug' if variant == 'Debug' else 'boulderbat'
        configs.append(add('config:' + name + variant, 'XCBuildConfiguration', name=variant, buildSettings=config))
    return add('configs:' + name, 'XCConfigurationList', buildConfigurations=configs, defaultConfigurationIsVisible=0, defaultConfigurationName='Release')

project_configs = configuration_list('project', base)
targets = {}
for name in products:
    is_widget = name.endswith('Widgets')
    is_watch = 'Watch' in name
    sources = shared + (widgets if is_widget else watch if is_watch else app)
    files = [add('build:' + name + ':' + path, 'PBXBuildFile', fileRef=source_refs[path]) for path in sources]
    phases = [add('sources:' + name, 'PBXSourcesBuildPhase', buildActionMask=2147483647, files=files, runOnlyForDeploymentPostprocessing=0),
              add('frameworks:' + name, 'PBXFrameworksBuildPhase', buildActionMask=2147483647, files=[], runOnlyForDeploymentPostprocessing=0),
              add('resources:' + name, 'PBXResourcesBuildPhase', buildActionMask=2147483647,
                  files=[add('assetbuild:' + name, 'PBXBuildFile', fileRef=assets)], runOnlyForDeploymentPostprocessing=0)]
    settings = dict(PRODUCT_NAME='$(TARGET_NAME)', PRODUCT_BUNDLE_IDENTIFIER='$(BOULDERBAT_APP_BUNDLE_IDENTIFIER)' + ('.watch.widgets' if is_watch and is_widget else '.watch' if is_watch else '.widgets' if is_widget else ''),
                    INFOPLIST_FILE='Configuration/' + ('Widget' if is_widget else 'Watch' if is_watch else 'App') + '-Info.plist',
                    SDKROOT='watchos' if is_watch else 'auto', SUPPORTED_PLATFORMS='watchos watchsimulator' if is_watch else 'iphoneos iphonesimulator macosx xros xrsimulator',
                    TARGETED_DEVICE_FAMILY='4' if is_watch else '1,2,7',
                    ENABLE_HARDENED_RUNTIME='YES', LD_RUNPATH_SEARCH_PATHS='$(inherited) @executable_path/Frameworks @executable_path/../Frameworks',
                    **{'CODE_SIGN_ENTITLEMENTS[sdk=macosx*]':'Configuration/App.entitlements'})
    if is_widget:
        # Let the system-hosted configuration form choose its accessible accent.
        # The app's yellow can otherwise appear on the editor's light gray rows.
        settings.update(APPLICATION_EXTENSION_API_ONLY='YES', SKIP_INSTALL='YES',
                        ASSETCATALOG_COMPILER_GLOBAL_ACCENT_COLOR_NAME='')
    else:
        settings['ASSETCATALOG_COMPILER_APPICON_NAME'] = 'AppIcon'
    if is_watch:
        settings['SKIP_INSTALL'] = 'YES'
    targets[name] = add('target:' + name, 'PBXNativeTarget', name=name, productName=name,
                        productReference=products[name], productType='com.apple.product-type.app-extension' if is_widget else 'com.apple.product-type.application',
                        buildConfigurationList=configuration_list(name, settings), buildPhases=phases, buildRules=[], dependencies=[])

for host, widget in [('Boulderbat', 'BoulderbatWidgets'), ('BoulderbatWatch', 'BoulderbatWatchWidgets')]:
    dependency = add('dependency:' + host + widget, 'PBXTargetDependency', target=targets[widget])
    objects[targets[host]]['dependencies'].append(dependency)
    file = add('embed:' + widget, 'PBXBuildFile', fileRef=products[widget], settings={'ATTRIBUTES':['RemoveHeadersOnCopy']})
    phase = add('embedphase:' + host, 'PBXCopyFilesBuildPhase', buildActionMask=2147483647, dstPath='', dstSubfolderSpec=13, files=[file], name='Embed Widget Extension', runOnlyForDeploymentPostprocessing=0)
    objects[targets[host]]['buildPhases'].append(phase)
# The watch companion is embedded only in iOS builds, not macOS/visionOS.
dependency = add('dependency:watch', 'PBXTargetDependency', target=targets['BoulderbatWatch'], platformFilters=['ios'])
objects[targets['Boulderbat']]['dependencies'].append(dependency)
file = add('embed:watch', 'PBXBuildFile', fileRef=products['BoulderbatWatch'], platformFilters=['ios'], settings={'ATTRIBUTES':['RemoveHeadersOnCopy']})
phase = add('embedphase:watch', 'PBXCopyFilesBuildPhase', buildActionMask=2147483647, dstPath='$(CONTENTS_FOLDER_PATH)/Watch', dstSubfolderSpec=16, files=[file], name='Embed Watch App', runOnlyForDeploymentPostprocessing=0)
objects[targets['Boulderbat']]['buildPhases'].append(phase)
project = add('project', 'PBXProject', attributes={'BuildIndependentTargetsInParallel':'YES', 'LastUpgradeCheck':'2700'},
              buildConfigurationList=project_configs, compatibilityVersion='Xcode 14.0', developmentRegion='en', hasScannedForEncodings=0,
              knownRegions=['en','Base'], mainGroup=main_group, productRefGroup=products_group, projectDirPath='', projectRoot='', targets=list(targets.values()))

def encode(value, level=0):
    indent='\t' * level
    if isinstance(value, dict):
        return '{\n' + ''.join('\t' * (level+1) + json.dumps(str(k)) + ' = ' + encode(v, level+1) + ';\n' for k,v in value.items()) + indent + '}'
    if isinstance(value, list):
        return '(\n' + ''.join('\t' * (level+1) + encode(v,level+1) + ',\n' for v in value) + indent + ')'
    if isinstance(value,int):return str(value)
    return json.dumps(value, ensure_ascii=False)
root = dict(archiveVersion=1, classes={}, objectVersion=60, objects=objects, rootObject=project)
(ROOT / 'Boulderbat.xcodeproj/project.pbxproj').write_text('// !$*UTF8*$!\n' + encode(root) + '\n')
for name in ['Boulderbat','BoulderbatWatch']:
    scheme = ET.Element('Scheme', LastUpgradeVersion='2700', version='1.3')
    build = ET.SubElement(scheme,'BuildAction',parallelizeBuildables='YES',buildImplicitDependencies='YES')
    entries = ET.SubElement(build,'BuildActionEntries')
    entry = ET.SubElement(entries,'BuildActionEntry',buildForTesting='YES',buildForRunning='YES',buildForProfiling='YES',buildForArchiving='YES',buildForAnalyzing='YES')
    def reference(parent):
        ET.SubElement(parent,'BuildableReference',BuildableIdentifier='primary',BlueprintIdentifier=targets[name],BuildableName=name+'.app',BlueprintName=name,ReferencedContainer='container:Boulderbat.xcodeproj')
    reference(entry)
    launch = ET.SubElement(scheme,'LaunchAction',buildConfiguration='Debug',selectedDebuggerIdentifier='Xcode.DebuggerFoundation.Debugger.LLDB',selectedLauncherIdentifier='Xcode.IDEFoundation.Launcher.LLDB',launchStyle='0',useCustomWorkingDirectory='NO',ignoresPersistentStateOnLaunch='NO',debugDocumentVersioning='YES',debugServiceExtension='internal',allowLocationSimulation='YES')
    reference(ET.SubElement(launch,'BuildableProductRunnable',runnableDebuggingMode='0'))
    ET.SubElement(scheme,'AnalyzeAction',buildConfiguration='Debug')
    ET.SubElement(scheme,'ArchiveAction',buildConfiguration='Release',revealArchiveInOrganizer='YES')
    ET.indent(scheme)
    (ROOT / f'Boulderbat.xcodeproj/xcshareddata/xcschemes/{name}.xcscheme').write_text(ET.tostring(scheme,encoding='unicode')+'\n')
print('Generated Boulderbat.xcodeproj (app, widget, watch app, watch widgets).')
