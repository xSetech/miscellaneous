# Scan for symlinks in $LOCAL/active that point to software installs with the
# typical Unixy structure (bin/, lib/, etc). The "installation" location is
# also referred to as a "prefix" (as in `./configure --prefix=...`).
#
# Special configuration files (placed in lib/ or lib64/ directories):
#   _config_no_l_flag           - If present, suppress the "-L<dir>" flag for this directory
#   _config_append_static_libs  - If present, append all static libraries (.a files) from
#                                 this directory directly to LDFLAGS with absolute paths
#   _config_prepend_static_libs - If present, prepend all static libraries (.a files) from
#                                 this directory before ALL -L entries in LDFLAGS
#   _config_ldflags             - If present, content is read and added to LDFLAGS for this directory
function configure_active_optional_software() {

    export ACTIVE_OPTIONAL_PATH=""
    export ACTIVE_OPTIONAL_LD_LIBRARY_PATH=""
    export ACTIVE_OPTIONAL_LDFLAGS=""
    export ACTIVE_OPTIONAL_CPPFLAGS=""
    export ACTIVE_OPTIONAL_CXXFLAGS=""
    export ACTIVE_OPTIONAL_MANPATH=""
    export ACTIVE_OPTIONAL_PKGCONFIG=""

    # Temporary variables to collect static libs that should be prepended
    local PREPEND_STATIC_LIBS=""
    local REGULAR_LDFLAGS=""

    # Helper function to process lib or lib64 directories
    function process_lib_dir() {
        local lib_dir=$1

        export ACTIVE_OPTIONAL_LD_LIBRARY_PATH="${ACTIVE_OPTIONAL_LD_LIBRARY_PATH}:${lib_dir}"

        # Handle static libraries based on configuration
        if [[ -e ${lib_dir}/_config_prepend_static_libs ]]; then
            # Collect static libs to prepend before ALL -L entries
            for static_lib in ${lib_dir}/*.a(N-.); do
                PREPEND_STATIC_LIBS="${PREPEND_STATIC_LIBS} ${static_lib}"
            done
        elif [[ -e ${lib_dir}/_config_append_static_libs ]]; then
            # Append static libraries before -L flag for this directory
            for static_lib in ${lib_dir}/*.a(N-.); do
                REGULAR_LDFLAGS="${REGULAR_LDFLAGS} ${static_lib}"
            done
        fi

        # Add custom LDFLAGS from _config_ldflags file
        if [[ -e ${lib_dir}/_config_ldflags ]]; then
            local custom_ldflags=$(cat ${lib_dir}/_config_ldflags)
            REGULAR_LDFLAGS="${REGULAR_LDFLAGS} ${custom_ldflags}"
        fi

        # Only add -L flag if _config_no_l_flag is not present
        if [[ ! -e ${lib_dir}/_config_no_l_flag ]]; then
            REGULAR_LDFLAGS="${REGULAR_LDFLAGS} -L${lib_dir}"
        fi
    }

    if [[ -d $LOCAL/active ]]; then

        echo "" >&2
        echo "Active optional software:" >&2

        pushd $LOCAL/active > /dev/null
        for active_entry in $(ls); do

            echo " * ${active_entry}" >&2

            if [[ -L ${active_entry} ]]; then
                local active_entry_abs_path=$(greadlink -m ${active_entry})
                if [[ -e ${active_entry_abs_path} ]]; then

                    if [[ -e ${active_entry_abs_path}/bin ]]; then
                        export ACTIVE_OPTIONAL_PATH="${ACTIVE_OPTIONAL_PATH}:${active_entry_abs_path}/bin"
                    fi

                    if [[ -e ${active_entry_abs_path}/sbin ]]; then
                        export ACTIVE_OPTIONAL_PATH="${ACTIVE_OPTIONAL_PATH}:${active_entry_abs_path}/sbin"
                    fi

                    if [[ -e ${active_entry_abs_path}/lib ]]; then
                        process_lib_dir ${active_entry_abs_path}/lib
                    fi

                    if [[ -e ${active_entry_abs_path}/lib64 ]]; then
                        process_lib_dir ${active_entry_abs_path}/lib64
                    fi

                    if [[ -e ${active_entry_abs_path}/include ]]; then
                        export ACTIVE_OPTIONAL_CPPFLAGS="${ACTIVE_OPTIONAL_CPPFLAGS} -I${active_entry_abs_path}/include"
                        export ACTIVE_OPTIONAL_CXXFLAGS="${ACTIVE_OPTIONAL_CXXFLAGS} -I${active_entry_abs_path}/include"
                    fi

                    if [[ -e ${active_entry_abs_path}/share/man ]]; then
                        export ACTIVE_OPTIONAL_MANPATH="${ACTIVE_OPTIONAL_MANPATH}:${active_entry_abs_path}/share/man"
                    fi

                    if [[ -e ${active_entry_abs_path}/pkgconfig ]]; then
                        export ACTIVE_OPTIONAL_PKGCONFIG="${ACTIVE_OPTIONAL_PKGCONFIG}:${active_entry_abs_path}/pkgconfig"
                    fi

                    if [[ -e ${active_entry_abs_path}/lib/pkgconfig ]]; then
                        export ACTIVE_OPTIONAL_PKGCONFIG="${ACTIVE_OPTIONAL_PKGCONFIG}:${active_entry_abs_path}/lib/pkgconfig"
                    fi

                    if [[ -e ${active_entry_abs_path}/share/pkgconfig ]]; then
                        export ACTIVE_OPTIONAL_PKGCONFIG="${ACTIVE_OPTIONAL_PKGCONFIG}:${active_entry_abs_path}/share/pkgconfig"
                    fi

                fi
            fi
        done
        popd > /dev/null

        # Construct final LDFLAGS: prepended static libs first, then regular flags
        export ACTIVE_OPTIONAL_LDFLAGS="${PREPEND_STATIC_LIBS}${REGULAR_LDFLAGS}"

        echo "" >&2
    fi
}
