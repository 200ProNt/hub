// Read-only Windows prototype for Benchmark Lab. Build with rustc -O.
use std::fs;
use std::io::{self, Write};
use std::os::windows::fs::MetadataExt;

fn main() -> io::Result<()> {
    let mut folder = String::new();
    io::stdin().read_line(&mut folder)?;
    let mut output = io::BufWriter::new(io::stdout().lock());
    for entry in fs::read_dir(folder.trim_end_matches(['\r', '\n']))?.take(250_000) {
        let entry = entry?;
        let info = entry.metadata()?;
        if info.is_file() && info.file_attributes() & 0x400 == 0 {
            let filename = entry.file_name().into_string().map_err(|_| {
                io::Error::new(io::ErrorKind::InvalidData, "filename is not Unicode")
            })?;
            writeln!(output, "{}\t{}", info.len(), filename)?;
        }
    }
    output.flush()
}
